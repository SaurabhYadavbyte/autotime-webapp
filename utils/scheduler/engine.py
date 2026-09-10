import collections
import copy
import time
from typing import List, Tuple

from utils.scheduler.core import TimeSlot, SessionOccurrence, GlobalState
from utils.scheduler.diagnostics import GenerationDiagnostics, ReasonCodes


class TimetableEngine:
    def __init__(self, time_slots: List[TimeSlot], days: List[str], lunch_after: int = 2, max_iterations=1000, seed=None, scheduler_config=None):
        self.time_slots = time_slots
        self.time_slots_by_index = {slot.idx: slot for slot in time_slots}
        self._slots_are_contiguous = set(self.time_slots_by_index) == set(
            range(len(time_slots))
        )
        self.days = days
        self.day_positions = {day: position for position, day in enumerate(days)}
        self.lunch_after = lunch_after
        # Retained for constructor compatibility. The current search is deadline-based,
        # not iteration- or random-seed-based.
        self.max_iterations = max_iterations
        self.seed = seed
        self.stats = self._new_stats()
        self.domains = {}
        self.teacher_deps = collections.defaultdict(list)
        self.class_deps = collections.defaultdict(list)
        self.failure_counts = collections.defaultdict(int)

        from utils.scheduler.core import SchedulerConfig

        config = scheduler_config or SchedulerConfig()
        self.max_generation_seconds = config.generation_timeout_seconds
        self.max_optimization_seconds = config.optimization_timeout_seconds
        self.max_optimization_iterations = config.optimization_max_iterations

        # perf_counter is monotonic and has enough resolution for small test and
        # production budgets on Windows.
        self._clock = time.perf_counter
        self.start_time = 0.0
        self._generation_deadline = None
        self._optimization_deadline = None
        self._search_timed_out = False

    @staticmethod
    def _new_stats():
        return {
            "candidates_evaluated": 0,
            "forward_check_calls": 0,
            "forward_check_failures": 0,
            "backtracks": 0,
            "backjumps": 0,
            "exhausted_search_frames": 0,
            "max_depth": 0,
            "optimization_attempts": 0,
            "optimization_accepted": 0,
            "swap_attempts": 0,
            "swap_accepted": 0,
            "feasibility_time": 0.0,
            "optimization_time": 0.0,
            "validation_time": 0.0,
            "total_time": 0.0,
        }

    def _generation_expired(self):
        deadline = self._generation_deadline
        if deadline is None:
            deadline = self.start_time + self.max_generation_seconds
        if self._clock() > deadline:
            self._search_timed_out = True
            return True
        return False

    def _optimization_expired(self):
        return (
            self._optimization_deadline is not None
            and self._clock() > self._optimization_deadline
        )

    @staticmethod
    def _restore_domains(domains, history):
        for unit_id, prior_domain in history:
            domains[unit_id] = prior_domain

    @staticmethod
    def _snapshot_inputs(units, state):
        assignments = [unit.assigned_slot for unit in units]
        state_values = {
            "teacher_busy": copy.deepcopy(state.teacher_busy),
            "class_busy": copy.deepcopy(state.class_busy),
            "teacher_hours": copy.deepcopy(state.teacher_hours),
        }
        return assignments, state_values

    @staticmethod
    def _restore_inputs(units, state, snapshot):
        assignments, state_values = snapshot
        for unit, assigned_slot in zip(units, assignments):
            unit.assigned_slot = assigned_slot
        state.teacher_busy = state_values["teacher_busy"]
        state.class_busy = state_values["class_busy"]
        state.teacher_hours = state_values["teacher_hours"]

    def _get_valid_candidates(
        self, unit: SessionOccurrence, state: GlobalState, deadline_check=None
    ) -> List[Tuple[str, int]]:
        candidates = []
        for day in self.days:
            if unit.preferred_days and day not in unit.preferred_days:
                continue

            if unit.teacher_id and unit.teacher_id in state.teacher_available_days:
                if day not in state.teacher_available_days[unit.teacher_id]:
                    continue

            max_start_idx = len(self.time_slots) - unit.duration
            for idx in range(max_start_idx + 1):
                if idx % 32 == 0 and deadline_check and deadline_check():
                    return candidates
                if not self._slots_are_contiguous and any(
                    slot_idx not in self.time_slots_by_index
                    for slot_idx in range(idx, idx + unit.duration)
                ):
                    continue
                # Multi-period continuity check (no crossing lunch)
                if unit.duration > 1:
                    if idx < self.lunch_after and (idx + unit.duration) > self.lunch_after:
                        continue

                if state.is_free(unit.teacher_id, unit.target_classes, day, idx, unit.duration):
                    candidates.append((day, idx))
        return candidates

    def _evaluate_candidate(
        self,
        unit: SessionOccurrence,
        state: GlobalState,
        day: str,
        idx: int,
        scheduled_units: List[SessionOccurrence],
        subject_day_counts=None,
    ) -> int:
        self.stats["candidates_evaluated"] += 1
        score = 0

        def class_has_class(c_id, d, i):
            return i in state.class_busy.get(c_id, {}).get(d, set())

        def teacher_has_class(t_id, d, i):
            if not t_id:
                return False
            return i in state.teacher_busy.get(t_id, {}).get(d, set())

        for c_id in unit.target_classes:
            adj_before = class_has_class(c_id, day, idx - 1) if idx > 0 else False
            adj_after = (
                class_has_class(c_id, day, idx + unit.duration)
                if idx + unit.duration < len(self.time_slots)
                else False
            )

            if adj_before or adj_after:
                score += 50
            else:
                score -= 30

        if unit.teacher_id:
            adj_before_t = teacher_has_class(unit.teacher_id, day, idx - 1) if idx > 0 else False
            adj_after_t = (
                teacher_has_class(unit.teacher_id, day, idx + unit.duration)
                if idx + unit.duration < len(self.time_slots)
                else False
            )

            if adj_before_t or adj_after_t:
                score += 30
            else:
                score -= 20

        # Subject distribution penalty
        if subject_day_counts is None:
            same_day_count = sum(
                1
                for scheduled_unit in scheduled_units
                if scheduled_unit.subject_id == unit.subject_id
                and scheduled_unit.assigned_slot
                and scheduled_unit.assigned_slot.day == day
            )
        else:
            same_day_count = subject_day_counts.get((unit.subject_id, day), 0)

        if same_day_count > 0:
            score -= 200

        return score

    def _forward_check_prune(self, assigned_unit: SessionOccurrence, state: GlobalState):
        self.stats["forward_check_calls"] += 1
        pruned_history = []
        affected_units = {}

        if assigned_unit.teacher_id:
            for f_u in self.teacher_deps[assigned_unit.teacher_id]:
                affected_units[f_u.id] = f_u
        for c_id in assigned_unit.target_classes:
            for f_u in self.class_deps[c_id]:
                affected_units[f_u.id] = f_u

        for f_unit in affected_units.values():
            if f_unit.assigned_slot is not None:
                continue

            prior_domain = self.domains[f_unit.id]
            new_domain = []
            for c_day, c_idx in prior_domain:
                if not state.is_free(
                    f_unit.teacher_id, f_unit.target_classes, c_day, c_idx, f_unit.duration
                ):
                    continue
                else:
                    new_domain.append((c_day, c_idx))

            if not new_domain:
                # This unit's domain was never replaced. Restore earlier replacements
                # byte-for-byte so neither order nor multiplicity can drift.
                self._restore_domains(self.domains, pruned_history)
                self.stats["forward_check_failures"] += 1
                return False, []

            if len(new_domain) != len(prior_domain):
                pruned_history.append((f_unit.id, prior_domain))
                self.domains[f_unit.id] = new_domain

        return True, pruned_history

    def _presolve(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> "GenerationDiagnostics":
        teacher_req = collections.defaultdict(int)
        class_req = collections.defaultdict(int)

        for u in units:
            if u.teacher_id:
                teacher_req[u.teacher_id] += u.duration
            for c in u.target_classes:
                class_req[c] += u.duration

        total_slots = len(self.time_slots) * len(self.days)

        for t_id, req in teacher_req.items():
            base_max = state.teacher_max_hours.get(t_id, total_slots)

            # Bound capacity by available days constraint
            if t_id in state.teacher_available_days:
                allowed_days = [d for d in self.days if d in state.teacher_available_days[t_id]]
                hard_max = len(allowed_days) * len(self.time_slots)
                max_h = min(base_max, hard_max)
            else:
                max_h = base_max
            if req > max_h:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_TEACHER_CAPACITY,
                    primary_bottleneck=f"Teacher: {t_id}",
                    affected_teachers=[t_id],
                    required_capacity=req,
                    available_capacity=max_h,
                    shortage=req - max_h,
                    suggestions=[
                        "Increase teacher maximum hours",
                        "Assign another teacher to some subjects",
                        "Reduce weekly requirement",
                    ],
                )

        for c_id, req in class_req.items():
            if req > total_slots:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_CLASS_CAPACITY,
                    primary_bottleneck="Class weekly load exceeds configured teaching capacity",
                    affected_courses=[c_id],
                    required_capacity=req,
                    available_capacity=total_slots,
                    shortage=req - total_slots,
                    suggestions=["Reduce total weekly hours for this class"],
                )

        return None

    def _solve(
        self, units: List[SessionOccurrence], state: GlobalState, depth: int
    ) -> Tuple[bool, List[SessionOccurrence], str]:
        if self._generation_expired():
            return False, [], "Generation timed out while searching for a feasible timetable."

        unassigned = [u for u in units if not u.assigned_slot]
        if not unassigned:
            return True, units, ""

        subject_day_counts = collections.Counter(
            (unit.subject_id, unit.assigned_slot.day)
            for unit in units
            if unit.assigned_slot
        )

        depth = len(units) - len(unassigned)
        if depth > self.stats["max_depth"]:
            self.stats["max_depth"] = depth

        min_domain = min(len(self.domains[u.id]) for u in unassigned)
        tied_domain = [u for u in unassigned if len(self.domains[u.id]) == min_domain]

        if not min_domain:
            # Short-circuit failure
            u = tied_domain[0]
            msg = f"Failed at {u.subject_name}. Teacher: {u.teacher_id}. No valid slots left."
            return False, [], msg

        if len(tied_domain) == 1:
            best_unit = tied_domain[0]
        else:
            # Apply scarcity tie-breaker
            def get_scarcity(u):
                s = 0
                if u.is_practical:
                    s += 50
                if len(u.target_classes) > 1:
                    s += 50
                return s

            scarcity_scores = [(get_scarcity(u), u) for u in tied_domain]
            max_scarcity = max(s[0] for s in scarcity_scores)
            tied_scarcity = [u for s, u in scarcity_scores if s == max_scarcity]

            if len(tied_scarcity) == 1:
                best_unit = tied_scarcity[0]
            else:
                # Regret tie-breaker ONLY for remaining tied units
                best_unit = None
                best_regret = -1
                for u in tied_scarcity:
                    if self._generation_expired():
                        return False, [], (
                            "Generation timed out while searching for a feasible timetable."
                        )
                    domain = self.domains[u.id]
                    if len(domain) == 1:
                        regret = 9999
                    else:
                        best_score = second_best = None
                        for candidate_index, (candidate_day, candidate_slot) in enumerate(domain):
                            if candidate_index % 32 == 0 and self._generation_expired():
                                return False, [], (
                                    "Generation timed out while searching for a feasible timetable."
                                )
                            score = self._evaluate_candidate(
                                u,
                                state,
                                candidate_day,
                                candidate_slot,
                                units,
                                subject_day_counts,
                            )
                            if best_score is None or score > best_score:
                                second_best, best_score = best_score, score
                            elif second_best is None or score > second_best:
                                second_best = score
                        regret = best_score - second_best

                    if regret > best_regret:
                        best_regret = regret
                        best_unit = u

        unit = best_unit
        candidates = list(self.domains[unit.id])

        if not candidates:
            self.failure_counts[unit.id] += 1
            msg = f"Failed at {unit.subject_name}. Teacher: {unit.teacher_id}. No valid slots left."
            return False, [], msg

        scored_candidates = []
        for candidate_index, (day, idx) in enumerate(candidates):
            if candidate_index % 32 == 0 and self._generation_expired():
                return False, [], "Generation timed out while searching for a feasible timetable."
            score = self._evaluate_candidate(
                unit, state, day, idx, units, subject_day_counts
            )
            scored_candidates.append((score, day, idx))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        for score, day, idx in scored_candidates:
            if self._generation_expired():
                return False, [], "Generation timed out while searching for a feasible timetable."

            state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            time_slot_obj = self.time_slots_by_index[idx]
            unit.assigned_slot = TimeSlot(
                day=day,
                idx=idx,
                start_time=time_slot_obj.start_time,
                end_time=self.time_slots_by_index[idx + unit.duration - 1].end_time,
            )

            fc_ok, pruned_history = self._forward_check_prune(unit, state)

            if fc_ok:
                success, result_units, msg = self._solve(units, state, depth + 1)
                if success:
                    return True, result_units, ""

            self.stats["backtracks"] += 1

            # Backtrack state and domains
            self._restore_domains(self.domains, pruned_history)

            unit.assigned_slot = None
            state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)

            if self._search_timed_out:
                return False, [], msg

        # Compatibility statistic: this counts exhausted recursive frames. The
        # implementation does not perform conflict-directed backjumping.
        self.stats["backjumps"] += 1
        self.stats["exhausted_search_frames"] += 1
        self.failure_counts[unit.id] += 1
        msg = f"Backtracking exhausted for {unit.subject_name}. All {len(candidates)} candidates led to future failures."
        return False, [], msg

    def _calculate_class_balance(
        self, state: "GlobalState", target_classes: List[str] = None
    ) -> int:
        penalty = 0
        c_ids = target_classes if target_classes else list(state.class_busy.keys())
        for c_id in c_ids:
            days_data = state.class_busy.get(c_id, {})
            actual_counts = [len(days_data.get(day, set())) for day in self.days]
            penalty += self._balance_penalty(actual_counts)
        return penalty

    @staticmethod
    def _balance_penalty(actual_counts) -> int:
        total_periods = sum(actual_counts)
        if total_periods == 0:
            return 0
        base_load, remainder = divmod(total_periods, len(actual_counts))
        base_penalty = sum(abs(actual - base_load) for actual in actual_counts)
        above_base = sum(actual > base_load for actual in actual_counts)
        raised_targets = min(remainder, above_base)
        return base_penalty - raised_targets + (remainder - raised_targets)

    def _calculate_exact_gaps(self, state: GlobalState) -> tuple[int, int]:
        return (
            self._gap_penalty(state.class_busy.values()),
            self._gap_penalty(state.teacher_busy.values()),
        )

    @staticmethod
    def _gap_penalty(schedules) -> int:
        penalty = 0
        for days_data in schedules:
            for slots in days_data.values():
                if slots:
                    penalty += max(slots) - min(slots) + 1 - len(slots)
        return penalty

    def _calculate_global_score(self, state: GlobalState) -> Tuple[int, int, int, int]:
        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        bal = self._calculate_class_balance(state)
        leading = self._calculate_leading_free_periods(state)
        return (c_gaps, bal, t_gaps, leading)

    def _calculate_local_score(
        self, teacher_id: str, target_classes: List[str], state: GlobalState
    ) -> Tuple[int, int, int, int]:
        teacher_ids = (teacher_id,) if teacher_id else ()
        return self._calculate_subset_score(state, teacher_ids, target_classes)

    def _calculate_subset_score(self, state, teacher_ids, class_ids):
        class_gaps = 0
        for class_id in class_ids:
            for slots in state.class_busy.get(class_id, {}).values():
                if slots:
                    class_gaps += max(slots) - min(slots) + 1 - len(slots)

        teacher_gaps = 0
        for teacher_id in teacher_ids:
            if not teacher_id:
                continue
            for slots in state.teacher_busy.get(teacher_id, {}).values():
                if slots:
                    teacher_gaps += max(slots) - min(slots) + 1 - len(slots)

        return (
            class_gaps,
            self._calculate_class_balance(state, class_ids),
            teacher_gaps,
            self._calculate_leading_free_periods(state, class_ids),
        )

    def _calculate_leading_free_periods(
        self, state: GlobalState, target_classes: List[str] = None
    ) -> int:
        penalty = 0
        c_ids = target_classes if target_classes else list(state.class_busy.keys())
        for c_id in c_ids:
            if c_id in state.class_busy:
                for day, slots in state.class_busy[c_id].items():
                    if slots:
                        penalty += min(slots)
        return penalty

    def _set_unit_slot(self, unit, state, day, idx):
        state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
        slot = self.time_slots_by_index[idx]
        unit.assigned_slot = TimeSlot(
            day=day,
            idx=idx,
            start_time=slot.start_time,
            end_time=self.time_slots_by_index[idx + unit.duration - 1].end_time,
        )

    @staticmethod
    def _slot_gap(slots):
        return max(slots) - min(slots) + 1 - len(slots) if slots else 0

    def _move_score_context(self, unit, state):
        class_context = []
        for class_id in unit.target_classes:
            days_data = state.class_busy.get(class_id, {})
            class_context.append(
                (
                    days_data,
                    [len(days_data.get(day, set())) for day in self.days],
                    self._gap_penalty((days_data,)),
                    sum(min(slots) for slots in days_data.values() if slots),
                )
            )

        teacher_context = None
        if unit.teacher_id:
            teacher_days = state.teacher_busy.get(unit.teacher_id, {})
            teacher_context = (teacher_days, self._gap_penalty((teacher_days,)))
        return class_context, teacher_context

    def _score_move(self, context, day, idx, duration):
        class_context, teacher_context = context
        last_idx = idx + duration - 1
        day_position = self.day_positions[day]
        class_gaps = balance = leading = 0

        for days_data, counts, base_gaps, base_leading in class_context:
            slots = days_data.get(day, set())
            old_gap = self._slot_gap(slots)
            new_min = min(min(slots), idx) if slots else idx
            new_max = max(max(slots), last_idx) if slots else last_idx
            new_gap = new_max - new_min + 1 - len(slots) - duration
            class_gaps += base_gaps - old_gap + new_gap
            leading += base_leading - (min(slots) if slots else 0) + new_min
            candidate_counts = counts.copy()
            candidate_counts[day_position] += duration
            balance += self._balance_penalty(candidate_counts)

        teacher_gaps = 0
        if teacher_context:
            days_data, base_gaps = teacher_context
            slots = days_data.get(day, set())
            old_gap = self._slot_gap(slots)
            new_min = min(min(slots), idx) if slots else idx
            new_max = max(max(slots), last_idx) if slots else last_idx
            new_gap = new_max - new_min + 1 - len(slots) - duration
            teacher_gaps = base_gaps - old_gap + new_gap

        return class_gaps, balance, teacher_gaps, leading

    def _try_best_move(self, unit, state):
        original_slot = unit.assigned_slot
        original_day, original_idx = original_slot.day, original_slot.idx
        old_score = self._calculate_local_score(unit.teacher_id, unit.target_classes, state)
        best_score = old_score
        best_move = None
        timed_out = False

        state.unassign(
            unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration
        )
        try:
            score_context = self._move_score_context(unit, state)
            candidates = self._get_valid_candidates(
                unit, state, self._optimization_expired
            )
            if self._optimization_expired():
                timed_out = True
            for candidate_index, (day, idx) in enumerate(candidates):
                if candidate_index % 16 == 0 and self._optimization_expired():
                    timed_out = True
                    break
                if day == original_day and idx == original_idx:
                    continue

                new_score = self._score_move(
                    score_context, day, idx, unit.duration
                )

                if new_score < best_score:
                    best_score = new_score
                    best_move = (day, idx)
        except Exception:
            state.assign(
                unit.teacher_id,
                unit.target_classes,
                original_day,
                original_idx,
                unit.duration,
            )
            raise

        if timed_out or best_move is None:
            state.assign(
                unit.teacher_id,
                unit.target_classes,
                original_day,
                original_idx,
                unit.duration,
            )
            return False, timed_out

        self._set_unit_slot(unit, state, *best_move)
        return True, False

    def _find_gap_slots(self, state):
        gaps = []
        for class_id, days_data in state.class_busy.items():
            for day, slots in days_data.items():
                if not slots:
                    continue
                for idx in range(min(slots), max(slots) + 1):
                    if idx not in slots:
                        gaps.append((class_id, day, idx))
        return gaps

    def _try_gap_swap(self, units, state):
        class_units = collections.defaultdict(list)
        units_by_slot = collections.defaultdict(list)
        for unit in units:
            if not unit.assigned_slot or unit.duration != 1:
                continue
            units_by_slot[(unit.assigned_slot.day, unit.assigned_slot.idx)].append(unit)
            for class_id in unit.target_classes:
                class_units[class_id].append(unit)

        for gap_class, gap_day, gap_idx in self._find_gap_slots(state):
            best_swap = None
            best_score = None
            candidates_b = [
                unit
                for unit in units_by_slot.get((gap_day, gap_idx), [])
                if gap_class not in unit.target_classes
            ]

            for unit_a in class_units.get(gap_class, []):
                if self._optimization_expired():
                    return False, True
                day_a, idx_a = unit_a.assigned_slot.day, unit_a.assigned_slot.idx
                if day_a == gap_day and idx_a == gap_idx:
                    continue

                for unit_b in candidates_b:
                    if self._optimization_expired():
                        return False, True
                    if unit_a.id == unit_b.id:
                        continue

                    self.stats["swap_attempts"] += 1
                    day_b, idx_b = unit_b.assigned_slot.day, unit_b.assigned_slot.idx
                    if unit_a.preferred_days and day_b not in unit_a.preferred_days:
                        continue
                    if unit_b.preferred_days and day_a not in unit_b.preferred_days:
                        continue

                    teachers = {unit_a.teacher_id, unit_b.teacher_id}
                    classes = set(unit_a.target_classes).union(unit_b.target_classes)
                    old_score = self._calculate_subset_score(state, teachers, classes)

                    state.unassign(
                        unit_a.teacher_id, unit_a.target_classes, day_a, idx_a, 1
                    )
                    state.unassign(
                        unit_b.teacher_id, unit_b.target_classes, day_b, idx_b, 1
                    )
                    new_score = None
                    try:
                        valid = state.is_free(
                            unit_a.teacher_id, unit_a.target_classes, day_b, idx_b, 1
                        ) and state.is_free(
                            unit_b.teacher_id, unit_b.target_classes, day_a, idx_a, 1
                        )
                        if valid:
                            state.assign(
                                unit_a.teacher_id, unit_a.target_classes, day_b, idx_b, 1
                            )
                            state.assign(
                                unit_b.teacher_id, unit_b.target_classes, day_a, idx_a, 1
                            )
                            try:
                                new_score = self._calculate_subset_score(
                                    state, teachers, classes
                                )
                            finally:
                                state.unassign(
                                    unit_b.teacher_id, unit_b.target_classes, day_a, idx_a, 1
                                )
                                state.unassign(
                                    unit_a.teacher_id, unit_a.target_classes, day_b, idx_b, 1
                                )
                    finally:
                        state.assign(
                            unit_a.teacher_id, unit_a.target_classes, day_a, idx_a, 1
                        )
                        state.assign(
                            unit_b.teacher_id, unit_b.target_classes, day_b, idx_b, 1
                        )

                    if self._optimization_expired():
                        return False, True
                    if new_score is not None and new_score < old_score:
                        if best_swap is None or new_score < best_score:
                            best_score = new_score
                            best_swap = (unit_a, unit_b, day_a, idx_a, day_b, idx_b)

            if best_swap:
                unit_a, unit_b, day_a, idx_a, day_b, idx_b = best_swap
                state.unassign(unit_a.teacher_id, unit_a.target_classes, day_a, idx_a, 1)
                state.unassign(unit_b.teacher_id, unit_b.target_classes, day_b, idx_b, 1)
                self._set_unit_slot(unit_a, state, day_b, idx_b)
                self._set_unit_slot(unit_b, state, day_a, idx_a)
                return True, False

        return False, False

    def _optimize(self, units: List[SessionOccurrence], state: GlobalState):
        self._optimization_deadline = self._clock() + self.max_optimization_seconds
        self.stats["optimization_attempts"] = 0
        self.stats["optimization_accepted"] = 0
        self.stats["swap_attempts"] = 0
        self.stats["swap_accepted"] = 0

        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        self.stats["class_internal_gaps_before"] = c_gaps
        self.stats["teacher_internal_gaps_before"] = t_gaps

        made_changes = True
        passes = 0
        while made_changes and passes < self.max_optimization_iterations:
            if self._optimization_expired():
                return
            made_changes = False
            passes += 1

            for unit in units:
                if not unit.assigned_slot:
                    continue
                if self._optimization_expired():
                    return
                self.stats["optimization_attempts"] += 1
                moved, timed_out = self._try_best_move(unit, state)
                if timed_out:
                    return
                if moved:
                    made_changes = True
                    self.stats["optimization_accepted"] += 1

            if passes == 1:
                c_gaps, t_gaps = self._calculate_exact_gaps(state)
                self.stats["class_internal_gaps_after_move"] = c_gaps
                self.stats["teacher_internal_gaps_after_move"] = t_gaps

            if not made_changes:
                swapped, timed_out = self._try_gap_swap(units, state)
                if timed_out:
                    return
                if swapped:
                    made_changes = True
                    self.stats["swap_accepted"] += 1

        # The former balance-repair phase repeated the same move candidates and
        # lexicographic local score after a no-change move pass, so it could not
        # accept anything the move pass had rejected.

    def _validate_timetable(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> Tuple[bool, str]:
        from utils.scheduler.validator import TimetableValidator
        valid_classes_set = set()
        for u in units:
            valid_classes_set.update(u.target_classes)

        is_valid, errors = TimetableValidator.audit(
            units=units,
            time_slots=self.time_slots,
            working_days=self.days,
            teacher_available_days=state.teacher_available_days,
            teacher_max_hours=state.teacher_max_hours,
            lunch_after=self.lunch_after,
            valid_classes=valid_classes_set,
        )
        if not is_valid:
            return False, errors[0]
        return True, "Valid"

    def generate(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> Tuple[bool, List[SessionOccurrence], str, dict, "GenerationDiagnostics"]:
        self.stats = self._new_stats()
        self.domains = {}
        self.teacher_deps = collections.defaultdict(list)
        self.class_deps = collections.defaultdict(list)
        self.failure_counts = collections.defaultdict(int)
        self._search_timed_out = False

        input_snapshot = self._snapshot_inputs(units, state)
        self.stats["required_periods"] = sum(unit.duration for unit in units)
        self.stats["scheduled_periods"] = 0
        self.stats["required_class_periods"] = sum(
            unit.duration * len(unit.target_classes) for unit in units
        )
        self.stats["scheduled_class_periods"] = 0
        t_start = self._clock()
        self.start_time = t_start
        self._generation_deadline = t_start + self.max_generation_seconds

        # Presolve Phase
        diag = self._presolve(units, state)
        if diag:
            self.stats["total_time"] = self._clock() - t_start
            return False, [], diag.reason_code, self.stats, diag

        # Initialize domains and dependencies
        for u in units:
            self.domains[u.id] = self._get_valid_candidates(
                u, state, self._generation_expired
            )
            if u.teacher_id:
                self.teacher_deps[u.teacher_id].append(u)
            for c_id in u.target_classes:
                self.class_deps[c_id].append(u)

        # Feasibility phase
        t_feas = self._clock()
        success, sched, msg = self._solve(units, state, 0)
        self.stats["feasibility_time"] = self._clock() - t_feas

        if not success:
            self._restore_inputs(units, state, input_snapshot)
            self.stats["total_time"] = self._clock() - t_start

            additional_pressure = None
            if self.failure_counts:
                hardest_unit_id = max(self.failure_counts.items(), key=lambda x: x[1])[0]
                hardest_unit = next((u for u in units if u.id == hardest_unit_id), None)
                if hardest_unit:
                    t_str = (
                        f"Prof. {hardest_unit.teacher_id}"
                        if hardest_unit.teacher_id
                        else "No Teacher"
                    )
                    additional_pressure = f"{hardest_unit.subject_name} ({t_str}) failed {self.failure_counts[hardest_unit_id]} times during deep search."

            is_timeout = self._search_timed_out
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code=ReasonCodes.SEARCH_TIMEOUT if is_timeout else ReasonCodes.NO_FEASIBLE_ASSIGNMENT,
                primary_bottleneck="Scheduling search exceeded its configured time budget." if is_timeout else "No valid timetable could be found under the enforced constraints.",
                additional_pressure=additional_pressure,
                bottleneck_stats=dict(self.failure_counts),
                suggestions=[
                    "Loosen constraints",
                    "Increase teacher maximum hours",
                    "Check consecutive periods required",
                ],
            )
            return False, sched, msg, self.stats, diag

        self.stats["scheduled_periods"] = sum(
            unit.duration for unit in sched if unit.assigned_slot
        )
        self.stats["scheduled_class_periods"] = sum(
            unit.duration * len(unit.target_classes)
            for unit in sched
            if unit.assigned_slot
        )

        # Optimization phase
        t_opt = self._clock()
        self._optimize(sched, state)
        self.stats["optimization_time"] = self._clock() - t_opt

        # Validation phase
        t_val = self._clock()
        v_ok, v_msg = self._validate_timetable(sched, state)
        self.stats["validation_time"] = self._clock() - t_val
        self.stats["total_time"] = self._clock() - t_start
        self.stats["total_sessions"] = len(units)

        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        self.stats["class_internal_gaps"] = c_gaps
        self.stats["teacher_internal_gaps"] = t_gaps
        self.stats["gap_penalty"] = self._calculate_global_score(state)[0]  # legacy compatibility

        if not v_ok:
            self._restore_inputs(units, state, input_snapshot)
            self.stats["scheduled_periods"] = 0
            self.stats["scheduled_class_periods"] = 0
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code=ReasonCodes.NO_FEASIBLE_ASSIGNMENT,
                primary_bottleneck=f"Validation failed: {v_msg}",
            )
            return False, sched, f"Validation failed: {v_msg}", self.stats, diag

        diag = GenerationDiagnostics(
            status="SUCCESS", reason_code="SUCCESS", primary_bottleneck=None
        )
        return True, sched, "Timetable generated successfully.", self.stats, diag
