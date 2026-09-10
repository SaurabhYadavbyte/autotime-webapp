from typing import List, Tuple
from .core import SessionOccurrence, TimeSlot

class TimetableValidator:
    """
    Independent validator to audit the global timetable before saving.
    Returns (is_valid, list_of_errors)
    """

    @staticmethod
    def audit(
        units: List[SessionOccurrence],
        time_slots: List[TimeSlot],
        working_days: List[str],
        teacher_available_days: dict,
        teacher_max_hours: dict,
        lunch_after: int,
        valid_classes: set = None
    ) -> Tuple[bool, List[str]]:
        errors = []

        teacher_schedule = {}  # teacher_id -> day -> set of indices
        class_schedule = {}  # class_id -> day -> set of indices
        teacher_workload = {}  # teacher_id -> total_hours
        seen_unit_ids = set()
        valid_slot_indices = {slot.idx for slot in time_slots}
        required_by_subject_class = {}
        scheduled_by_subject_class = {}

        # Group by session_group_id to check shared logic if applicable
        # Actually in this model, SessionOccurrence itself can have multiple target_classes.
        # target_classes handles shared sessions.

        # First pass: Check assignments, bounds, working days, continuity, double booking
        for unit in units:
            if unit.id in seen_unit_ids:
                errors.append(f"Hard Constraint Violation: Duplicate logical occurrence '{unit.id}' detected.")
            seen_unit_ids.add(unit.id)

            required_periods = getattr(unit, "required_periods", None)
            if required_periods is not None:
                for c_id in unit.target_classes:
                    key = (unit.subject_id, c_id)
                    previous = required_by_subject_class.setdefault(
                        key, (unit.subject_name, required_periods)
                    )
                    if previous[1] != required_periods:
                        errors.append(
                            "Hard Constraint Violation: inconsistent required periods "
                            f"for {unit.subject_name} and class {c_id}."
                        )

            if not unit.assigned_slot:
                errors.append(
                    f"Hard Constraint Violation: {unit.subject_name} for classes {unit.target_classes} is not assigned a slot."
                )
                continue

            day = unit.assigned_slot.day
            start_idx = unit.assigned_slot.idx

            if day not in working_days:
                errors.append(f"Hard Constraint Violation: {unit.subject_name} assigned to {day}, which is not a configured working day.")

            if unit.preferred_days and day not in unit.preferred_days:
                errors.append(
                    f"Hard Constraint Violation: {unit.subject_name} assigned to {day}, "
                    "which is outside its preferred-day restriction."
                )

            if not unit.target_classes:
                errors.append(
                    f"Hard Constraint Violation: {unit.subject_name} has no target class."
                )

            # Continuity / Bounds / Lunch
            occupied_indices = range(start_idx, start_idx + unit.duration)
            if (
                start_idx < 0
                or unit.duration < 1
                or any(idx not in valid_slot_indices for idx in occupied_indices)
            ):
                errors.append(f"Hard Constraint Violation: {unit.subject_name} exceeds day bounds.")
                continue

            if unit.duration > 1:
                # Multi-period continuity across the lunch boundary is prohibited.
                if start_idx < lunch_after and (start_idx + unit.duration) > lunch_after:
                    errors.append(f"Hard Constraint Violation: {unit.subject_name} (duration {unit.duration}) crosses the lunch boundary at period {lunch_after}.")

            for i in range(unit.duration):
                idx = start_idx + i

                # Teacher constraints
                if unit.teacher_id:
                    if unit.teacher_id not in teacher_max_hours:
                        errors.append(f"Hard Constraint Violation: Assigned Teacher {unit.teacher_id} is unknown.")

                    if idx in teacher_schedule.get(unit.teacher_id, {}).get(day, set()):
                        errors.append(
                            f"Hard Constraint Violation: Teacher {unit.teacher_id} is double-booked on {day} at slot index {idx}."
                        )

                    if teacher_available_days and unit.teacher_id in teacher_available_days:
                        if day not in teacher_available_days[unit.teacher_id]:
                            errors.append(
                                f"Hard Constraint Violation: Teacher {unit.teacher_id} is assigned on {day} but is not available."
                            )

                    teacher_schedule.setdefault(unit.teacher_id, {}).setdefault(day, set()).add(idx)
                    teacher_workload[unit.teacher_id] = teacher_workload.get(unit.teacher_id, 0) + 1

                # Class constraints
                for c_id in unit.target_classes:
                    if valid_classes is not None and c_id not in valid_classes:
                        errors.append(f"Hard Constraint Violation: Assigned Class {c_id} is unknown.")

                    if idx in class_schedule.get(c_id, {}).get(day, set()):
                        errors.append(
                            f"Hard Constraint Violation: Class {c_id} is double-booked on {day} at slot index {idx}."
                        )
                    class_schedule.setdefault(c_id, {}).setdefault(day, set()).add(idx)

            if required_periods is not None:
                for c_id in unit.target_classes:
                    key = (unit.subject_id, c_id)
                    scheduled_by_subject_class[key] = (
                        scheduled_by_subject_class.get(key, 0) + unit.duration
                    )

        # Second pass: Check workload
        for t_id, hours in teacher_workload.items():
            if t_id in teacher_max_hours:
                if hours > teacher_max_hours[t_id]:
                    errors.append(f"Hard Constraint Violation: Teacher {t_id} exceeds max workload ({hours} > {teacher_max_hours[t_id]}).")

        for key, (subject_name, required_periods) in required_by_subject_class.items():
            scheduled_periods = scheduled_by_subject_class.get(key, 0)
            if scheduled_periods != required_periods:
                errors.append(
                    "Hard Constraint Violation: "
                    f"{subject_name} for class {key[1]} requires {required_periods} periods "
                    f"but has {scheduled_periods}."
                )

        return len(errors) == 0, errors
