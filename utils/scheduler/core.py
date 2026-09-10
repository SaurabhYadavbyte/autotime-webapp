from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple, Optional


@dataclass
class TimeSlot:
    day: str
    idx: int
    start_time: str
    end_time: str


@dataclass
class SessionOccurrence:
    id: str  # Unique ID (e.g., SUBJ_ID_1)
    subject_id: int
    subject_name: str
    teacher_id: str
    target_classes: List[str]  # Handles common subjects easily
    duration: int
    preferred_days: List[str]
    is_practical: bool

    # State tracking for backtracking
    assigned_slot: Optional[TimeSlot] = None


@dataclass
class GlobalState:
    # Expected O(1) membership lookups
    teacher_busy: Dict[str, Dict[str, Set[int]]] = field(
        default_factory=dict
    )  # teacher_id -> day -> set of slot idx
    class_busy: Dict[str, Dict[str, Set[int]]] = field(
        default_factory=dict
    )  # class_id -> day -> set of slot idx

    # Workload tracking. Legacy "hours" names count teaching periods, not clock hours.
    teacher_hours: Dict[str, int] = field(default_factory=dict)
    teacher_max_hours: Dict[str, int] = field(default_factory=dict)
    teacher_available_days: Dict[str, Set[str]] = field(
        default_factory=dict
    )  # teacher_id -> set of allowed day_names

    # Future scaling
    # room_busy: Dict[str, Dict[str, Set[int]]] = field(default_factory=dict)

    def is_free(
        self, teacher_id: str, classes: List[str], day: str, slot_idx: int, duration: int
    ) -> bool:
        if teacher_id:
            # Check weekly maximum workload
            if teacher_id in self.teacher_max_hours:
                if (
                    self.teacher_hours.get(teacher_id, 0) + duration
                    > self.teacher_max_hours[teacher_id]
                ):
                    return False

            # Check hard availability constraint for this specific day
            if teacher_id in self.teacher_available_days:
                if day not in self.teacher_available_days[teacher_id]:
                    return False

        for i in range(duration):
            curr_idx = slot_idx + i
            if teacher_id:
                if curr_idx in self.teacher_busy.get(teacher_id, {}).get(day, set()):
                    return False
            for cls in classes:
                if curr_idx in self.class_busy.get(cls, {}).get(day, set()):
                    return False
        return True

    def assign(self, teacher_id: str, classes: List[str], day: str, slot_idx: int, duration: int):
        for i in range(duration):
            curr_idx = slot_idx + i
            if teacher_id:
                self.teacher_busy.setdefault(teacher_id, {}).setdefault(day, set()).add(curr_idx)
            for cls in classes:
                self.class_busy.setdefault(cls, {}).setdefault(day, set()).add(curr_idx)

        if teacher_id:
            self.teacher_hours[teacher_id] = self.teacher_hours.get(teacher_id, 0) + duration

    def unassign(self, teacher_id: str, classes: List[str], day: str, slot_idx: int, duration: int):
        for i in range(duration):
            curr_idx = slot_idx + i
            if teacher_id:
                self.teacher_busy.get(teacher_id, {}).get(day, set()).discard(curr_idx)
            for cls in classes:
                self.class_busy.get(cls, {}).get(day, set()).discard(curr_idx)

        if teacher_id:
            self.teacher_hours[teacher_id] = max(
                0, self.teacher_hours.get(teacher_id, 0) - duration
            )

@dataclass
class SchedulerConfig:
    generation_timeout_seconds: float = 3.0
    optimization_timeout_seconds: float = 1.0
    optimization_max_iterations: int = 2
