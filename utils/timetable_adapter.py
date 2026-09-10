import copy

from models import Course, GenerationHistory, Institute, Subject, Teacher, Timetable, db
from utils.helpers import get_dynamic_time_slots, ScheduleConfig


def engine_generate_timetable(inst_code):
    from utils.scheduler import (
        TimeSlot,
        SessionOccurrence,
        GlobalState,
        TimetableEngine,
        TimetableValidator,
    )
    import json
    # Defer deletion of the existing timetable until successful generation
    # to maintain database transaction safety.

    institute = Institute.query.filter_by(institute_code=inst_code).first()
    if not institute:
        return {
            "success": False,
            "status": "FAILED",
            "message": "Institute not found.",
            "stats": {},
            "diagnostics": None,
        }
    institute_id = institute.id

    subjects = Subject.query.filter_by(institute_code=inst_code).all()
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    courses = Course.query.filter_by(institute_code=inst_code).all()

    teacher_dict = {t.teacher_id: t for t in teachers}
    course_dict = {course.class_id: course for course in courses}
    schedule_config = ScheduleConfig(inst_code)
    raw_slots = schedule_config.get_dynamic_time_slots()
    days = schedule_config.working_days

    time_slots = []
    for idx, (st, et) in enumerate(raw_slots):
        time_slots.append(TimeSlot(day="", idx=idx, start_time=st, end_time=et))

    state = GlobalState()
    for t in teachers:
        state.teacher_max_hours[t.teacher_id] = t.max_hours

        # Parse available days
        if t.available_days:
            parsed_days = {d.strip() for d in t.available_days.split(",")}
            state.teacher_available_days[t.teacher_id] = parsed_days
        else:
            # Documented backward-compatibility: Missing means all working days
            state.teacher_available_days[t.teacher_id] = set(days)

    units = []
    invalid_requirements = []
    original_required_periods = 0
    original_required_class_periods = 0

    for sub in subjects:
        # Determine target classes
        if "," in sub.class_id:
            target_classes = [c.strip() for c in sub.class_id.split(",") if c.strip()]
        else:
            target_classes = [sub.class_id.strip()]

        t_id = sub.teacher_id if sub.teacher_id else ""

        pref_days = []
        if sub.preferred_days:
            pref_days = [d.strip() for d in sub.preferred_days.split(",") if d.strip()]

        is_prac = sub.subject_type and sub.subject_type.lower() == "practical"

        # Weekly "hours" are teaching periods. Existing input rules require each
        # subject to be composed of full, fixed-length sessions.
        required_periods = sub.required_hours
        session_len = sub.session_length if sub.session_length is not None else 1
        if required_periods is not None and required_periods > 0:
            original_required_periods += required_periods
            original_required_class_periods += required_periods * len(target_classes)
        if (
            required_periods is None
            or required_periods <= 0
            or session_len <= 0
            or required_periods % session_len
        ):
            invalid_requirements.append(sub)
            continue

        num_sessions = required_periods // session_len

        for i in range(num_sessions):
            unit = SessionOccurrence(
                id=f"{sub.id}_{i}",
                subject_id=sub.id,
                subject_name=sub.subject_name,
                teacher_id=t_id,
                target_classes=target_classes,
                duration=session_len,
                preferred_days=pref_days,
                is_practical=is_prac,
            )
            # Adapter metadata lets the independent validator compare generated
            # occurrences with the source requirement without changing the
            # public SessionOccurrence constructor.
            unit.required_periods = required_periods
            units.append(unit)

    if invalid_requirements:
        from utils.scheduler.diagnostics import GenerationDiagnostics, ReasonCodes

        affected_subjects = [subject.subject_name for subject in invalid_requirements]
        msg = (
            "Invalid weekly period requirement: required_hours must be positive and "
            "divisible by session_length."
        )
        stats = {
            "feasibility_time": 0.0,
            "optimization_time": 0.0,
            "validation_time": 0.0,
            "total_time": 0.0,
            "total_sessions": 0,
            "required_periods": original_required_periods,
            "scheduled_periods": 0,
            "required_class_periods": original_required_class_periods,
            "scheduled_class_periods": 0,
        }
        diag = GenerationDiagnostics(
            status="FAILED",
            reason_code=ReasonCodes.INVALID_SUBJECT_REQUIREMENT,
            primary_bottleneck=msg,
            affected_subjects=affected_subjects,
            suggestions=[
                "Set each subject's required weekly periods to a positive multiple of its session length."
            ],
            statistics={"invalid_subject_count": len(invalid_requirements)},
        )
        success = False
        scheduled_units = []
    else:
        engine = TimetableEngine(
            time_slots=time_slots,
            days=days,
            lunch_after=schedule_config.lunch_after,
        )
        success, scheduled_units, msg, stats, diag = engine.generate(units, state)

    if success:
        # Validate
        valid_classes_set = set(course_dict.keys())
        is_valid, errors = TimetableValidator.audit(
            units=scheduled_units,
            time_slots=time_slots,
            working_days=days,
            teacher_available_days=state.teacher_available_days,
            teacher_max_hours=state.teacher_max_hours,
            lunch_after=schedule_config.lunch_after,
            valid_classes=valid_classes_set,
        )
        if not is_valid:
            success = False
            msg = f"Validation failed: {errors[0]}"
            from utils.scheduler.diagnostics import GenerationDiagnostics

            diag = GenerationDiagnostics(
                status="FAILED", reason_code="VALIDATION_FAILED", primary_bottleneck=msg
            )

    if success:
        # Transaction Safety: Delete old timetable only when replacement is ready
        Timetable.query.filter_by(institute_code=inst_code, specific_date=None).delete()

        records_to_add = []
        for unit in scheduled_units:
            disp_name = (
                f"{unit.subject_name} (Practical)" if unit.is_practical else unit.subject_name
            )
            teacher = teacher_dict.get(unit.teacher_id)
            t_name = teacher.name if teacher else unit.teacher_id
            t_id_fk = teacher.id if teacher else None
            s_id_fk = getattr(unit, "subject_id", None)

            for c_id in unit.target_classes:
                course_match = course_dict.get(c_id)
                c_id_fk = course_match.id if course_match else None

                for offset in range(unit.duration):
                    actual_slot = time_slots[unit.assigned_slot.idx + offset]
                    new_entry = Timetable(
                        institute_id=institute_id,
                        institute_code=inst_code,
                        course_id_fk=c_id_fk,
                        teacher_id_fk=t_id_fk,
                        subject_id_fk=s_id_fk,
                        session_group_id=unit.id,
                        class_id=c_id,
                        day_name=unit.assigned_slot.day,
                        start_time=actual_slot.start_time,
                        end_time=actual_slot.end_time,
                        subject_name=disp_name,
                        teacher_name=t_name,
                        is_proxy=False,
                    )
                    records_to_add.append(new_entry)

        db.session.bulk_save_objects(records_to_add)

    # Record to GenerationHistory
    gap_score = stats.get("gap_penalty") if success else None
    history = GenerationHistory(
        institute_id=institute_id,
        institute_code=inst_code,
        status="SUCCESS" if success else "FAILED",
        sessions_count=len(scheduled_units) if scheduled_units else 0,
        generation_time=stats.get("feasibility_time", 0),
        optimization_time=stats.get("optimization_time", 0),
        gap_score=gap_score,
        primary_failure_reason=diag.primary_bottleneck if diag else None,
        diagnostics_json=json.dumps(diag.to_dict()) if diag else None,
    )
    db.session.add(history)
    db.session.commit()

    if success:
        stats["logical_session_occurrences"] = len(scheduled_units)
        stats["occupied_class_periods"] = sum(
            unit.duration * len(unit.target_classes) for unit in scheduled_units
        )
    else:
        stats["logical_session_occurrences"] = 0
        stats["occupied_class_periods"] = 0

    result = {
        "success": success,
        "status": "SUCCESS" if success else "FAILED",
        "message": msg,
        "stats": stats,
        "diagnostics": diag.to_dict() if diag else None,
    }

    return result


def get_effective_timetable(inst_code, filters=None, target_date=None):
    """
    Fetches the timetable and applies date-specific proxy overrides.
    Returns a list of Timetable objects representing the effective schedule.
    """
    if filters is None:
        filters = {}

    pre_merge_filters = {"institute_code": inst_code}
    if "class_id" in filters:
        pre_merge_filters["class_id"] = filters["class_id"]

    # 1. Fetch master timetable (specific_date is NULL)
    master_records = Timetable.query.filter_by(**pre_merge_filters, specific_date=None).all()

    # 2. Fetch overrides
    if target_date:
        override_records = Timetable.query.filter_by(**pre_merge_filters, specific_date=target_date).all()
    else:
        override_records = []

    # 3. Merge
    effective_dict = {}
    for r in master_records:
        key = (r.class_id, r.day_name, r.start_time)
        effective_dict[key] = r

    for r in override_records:
        key = (r.class_id, r.day_name, r.start_time)
        effective_dict[key] = r

    # 4. Post-merge filter by teacher identity to maintain operational accuracy
    final_records = []
    t_name_filter = filters.get("teacher_name")
    t_id_filter = filters.get("teacher_id_fk")

    for record in effective_dict.values():
        if record.teacher_name == "__UNCOVERED__":
            record = copy.copy(record)
            record.teacher_name = "Teacher on Leave / Proxy Not Assigned"

        if t_name_filter and record.teacher_name != t_name_filter:
            continue
        if t_id_filter and record.teacher_id_fk != t_id_filter:
            continue

        final_records.append(record)

    return final_records


def get_live_week_timetable(inst_code, reference_date=None, filters=None):
    """
    Calculates the real current week and returns the effective timetable
    incorporating day-specific overrides for all configured working days.
    """
    from utils.helpers import get_local_date, ScheduleConfig
    from datetime import timedelta

    if not reference_date:
        reference_date = get_local_date()

    schedule_config = ScheduleConfig(inst_code)
    working_days = schedule_config.working_days

    # Python weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    day_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

    ref_weekday = reference_date.weekday()
    start_of_week = reference_date - timedelta(days=ref_weekday)

    day_dates = {}
    for i in range(7):
        d = start_of_week + timedelta(days=i)
        day_name = day_map[d.weekday()]
        if day_name in working_days:
            day_dates[day_name] = d

    if filters is None:
        filters = {}

    pre_merge_filters = {"institute_code": inst_code}
    if "class_id" in filters:
        pre_merge_filters["class_id"] = filters["class_id"]

    # Bulk fetch master for working days
    master_records = Timetable.query.filter_by(**pre_merge_filters, specific_date=None).filter(
        Timetable.day_name.in_(working_days)
    ).all()

    # Bulk fetch overrides for the calculated dates
    date_list = list(day_dates.values())
    override_records = Timetable.query.filter_by(**pre_merge_filters).filter(
        Timetable.specific_date.in_(date_list)
    ).all()

    effective_dict = {}
    for r in master_records:
        key = (r.class_id, r.day_name, r.start_time)
        effective_dict[key] = r

    for r in override_records:
        # Only override if it matches the calculated date for that day
        if day_dates.get(r.day_name) == r.specific_date:
            key = (r.class_id, r.day_name, r.start_time)
            effective_dict[key] = r

    final_records = []
    t_name_filter = filters.get("teacher_name")
    t_id_filter = filters.get("teacher_id_fk")

    for record in effective_dict.values():
        if record.teacher_name == "__UNCOVERED__":
            record = copy.copy(record)
            record.teacher_name = "Teacher on Leave / Proxy Not Assigned"

        if t_name_filter and record.teacher_name != t_name_filter:
            continue
        if t_id_filter and record.teacher_id_fk != t_id_filter:
            continue

        final_records.append(record)

    return {
        "week_start": start_of_week,
        "week_end": start_of_week + timedelta(days=6),
        "working_days": working_days,
        "day_dates": day_dates,
        "records": final_records
    }
