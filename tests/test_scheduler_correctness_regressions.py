import copy

from models import Course, Institute, Settings, Subject, Teacher, Timetable, db
from utils.scheduler.core import GlobalState, SessionOccurrence, TimeSlot
from utils.scheduler.engine import TimetableEngine
from utils.scheduler.validator import TimetableValidator
from utils.timetable_adapter import engine_generate_timetable


class ControlledClock:
    def __init__(self, values):
        self.values = iter(values)
        self.last = 0.0

    def __call__(self):
        self.last = next(self.values, self.last)
        return self.last


def test_forward_check_wipeout_restores_exact_domains():
    slots = [TimeSlot("", idx, str(idx), str(idx + 1)) for idx in range(2)]
    engine = TimetableEngine(slots, ["Mon"])
    assigned = SessionOccurrence("assigned", 1, "A", "T1", ["C0"], 1, [], False)
    reordered = SessionOccurrence("reordered", 2, "B", "T1", ["C1"], 1, [], False)
    wiped_out = SessionOccurrence("wiped", 3, "C", "T1", ["C2"], 1, [], False)
    engine.teacher_deps["T1"] = [reordered, wiped_out]
    engine.domains = {
        reordered.id: [("Mon", 0), ("Mon", 1)],
        wiped_out.id: [("Mon", 0)],
    }
    original_domains = copy.deepcopy(engine.domains)
    state = GlobalState()
    state.assign("T1", assigned.target_classes, "Mon", 0, 1)

    success, history = engine._forward_check_prune(assigned, state)

    assert not success
    assert history == []
    assert engine.domains == original_domains


def test_search_timeout_rolls_back_assignments_state_and_domains():
    slots = [TimeSlot("", 0, "08:00", "09:00")]
    engine = TimetableEngine(slots, ["Mon"])
    engine.start_time = 0.0
    engine.max_generation_seconds = 1.0
    engine._clock = ControlledClock([0.0, 0.0, 0.0, 2.0])

    unit = SessionOccurrence("u1", 1, "Math", "T1", ["C1"], 1, [], False)
    engine.domains = {unit.id: [("Mon", 0)]}
    engine.teacher_deps["T1"] = [unit]
    engine.class_deps["C1"] = [unit]
    original_domains = copy.deepcopy(engine.domains)
    state = GlobalState(teacher_max_hours={"T1": 2})

    success, scheduled, message = engine._solve([unit], state, 0)

    assert not success
    assert scheduled == []
    assert "timed out" in message
    assert unit.assigned_slot is None
    assert state.teacher_hours.get("T1", 0) == 0
    assert not state.teacher_busy.get("T1", {}).get("Mon", set())
    assert not state.class_busy.get("C1", {}).get("Mon", set())
    assert engine.domains == original_domains


def test_optimizer_timeout_restores_unassigned_move():
    slots = [TimeSlot("", idx, str(idx), str(idx + 1)) for idx in range(3)]
    engine = TimetableEngine(slots, ["Mon"])
    engine.max_optimization_seconds = 1.0
    engine._clock = ControlledClock([0.0, 0.0, 0.0, 2.0])
    unit = SessionOccurrence(
        "u1",
        1,
        "Math",
        "T1",
        ["C1"],
        1,
        [],
        False,
        assigned_slot=TimeSlot("Mon", 2, "2", "3"),
    )
    state = GlobalState(teacher_max_hours={"T1": 2})
    state.assign("T1", ["C1"], "Mon", 2, 1)
    original_state = copy.deepcopy(state)

    engine._optimize([unit], state)

    assert unit.assigned_slot.idx == 2
    assert state == original_state


def test_move_score_reuse_matches_full_recalculation():
    days = ["Mon", "Tue", "Wed"]
    slots = [TimeSlot("", idx, str(idx), str(idx + 1)) for idx in range(4)]
    engine = TimetableEngine(slots, days)
    state = GlobalState(teacher_max_hours={"T1": 10})
    state.assign("T1", ["C1"], "Mon", 0, 1)
    state.assign("T1", ["C2"], "Tue", 2, 1)
    unit = SessionOccurrence("u", 1, "Shared", "T1", ["C1", "C2"], 1, [], False)
    context = engine._move_score_context(unit, state)

    predicted = engine._score_move(context, "Wed", 1, 1)
    state.assign("T1", ["C1", "C2"], "Wed", 1, 1)
    actual = engine._calculate_local_score("T1", ["C1", "C2"], state)
    state.unassign("T1", ["C1", "C2"], "Wed", 1, 1)

    assert predicted == actual


def test_swap_timeout_restores_trial_state():
    slots = [TimeSlot("", idx, str(idx), str(idx + 1)) for idx in range(3)]
    engine = TimetableEngine(slots, ["Mon"])
    engine._clock = ControlledClock([0.0, 0.0, 2.0])
    engine._optimization_deadline = 1.0
    units = [
        SessionOccurrence(
            "a1", 1, "A1", "T1", ["A"], 1, [], False,
            assigned_slot=TimeSlot("Mon", 0, "0", "1"),
        ),
        SessionOccurrence(
            "a2", 2, "A2", "T2", ["A"], 1, [], False,
            assigned_slot=TimeSlot("Mon", 2, "2", "3"),
        ),
        SessionOccurrence(
            "b1", 3, "B1", "T2", ["B"], 1, [], False,
            assigned_slot=TimeSlot("Mon", 1, "1", "2"),
        ),
    ]
    state = GlobalState(teacher_max_hours={"T1": 5, "T2": 5})
    for unit in units:
        state.assign(
            unit.teacher_id,
            unit.target_classes,
            unit.assigned_slot.day,
            unit.assigned_slot.idx,
            unit.duration,
        )
    original_state = copy.deepcopy(state)
    original_slots = [unit.assigned_slot for unit in units]

    swapped, timed_out = engine._try_gap_swap(units, state)

    assert timed_out
    assert not swapped
    assert state == original_state
    assert [unit.assigned_slot for unit in units] == original_slots


def test_validator_checks_original_required_periods():
    slots = [TimeSlot("", idx, str(idx), str(idx + 1)) for idx in range(4)]
    units = [
        SessionOccurrence(
            f"u{idx}", 1, "Lab", "T1", ["C1"], 2, [], True,
            assigned_slot=TimeSlot("Mon", idx * 2, str(idx * 2), str(idx * 2 + 2)),
        )
        for idx in range(2)
    ]
    for unit in units:
        unit.required_periods = 6

    valid, errors = TimetableValidator.audit(
        units, slots, ["Mon"], {"T1": {"Mon"}}, {"T1": 10}, 4, {"C1"}
    )

    assert not valid
    assert any("requires 6 periods but has 4" in error for error in errors)


def test_validator_checks_preferred_day_restriction():
    slots = [TimeSlot("", 0, "08:00", "09:00")]
    unit = SessionOccurrence(
        "u1", 1, "Math", "T1", ["C1"], 1, ["Tue"], False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00"),
    )

    valid, errors = TimetableValidator.audit(
        [unit], slots, ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 2}, 1,
        {"C1"},
    )

    assert not valid
    assert any("outside its preferred-day restriction" in error for error in errors)


def test_shared_session_counts_teacher_once_and_each_class():
    slots = [TimeSlot("", 0, "08:00", "09:00")]
    engine = TimetableEngine(slots, ["Mon"])
    state = GlobalState(
        teacher_max_hours={"T1": 1},
        teacher_available_days={"T1": {"Mon"}},
    )
    unit = SessionOccurrence(
        "shared", 1, "Common", "T1", ["C1", "C2"], 1, [], False,
    )
    unit.required_periods = 1

    success, _, _, stats, _ = engine.generate([unit], state)

    assert success
    assert state.teacher_hours["T1"] == 1
    assert stats["scheduled_periods"] == 1
    assert stats["scheduled_class_periods"] == 2


def test_nondivisible_required_periods_fail_without_replacing_timetable(app):
    with app.app_context():
        institute_id = Institute.query.filter_by(institute_code="TEST01").one().id
        course = Course(
            institute_id=institute_id,
            institute_code="TEST01",
            class_id="C1",
            department="CS",
            semester=1,
            division="A",
        )
        teacher = Teacher(
            institute_id=institute_id,
            institute_code="TEST01",
            teacher_id="T1",
            name="Teacher",
            email="teacher@example.com",
            departments="CS",
            available_days="Mon,Tue,Wed,Thu,Fri,Sat",
            max_hours=10,
        )
        db.session.add_all([course, teacher])
        db.session.flush()
        subject = Subject(
            institute_id=institute_id,
            institute_code="TEST01",
            subject_code="S1",
            subject_name="Lab",
            class_id="C1",
            teacher_id="T1",
            teacher_id_fk=teacher.id,
            required_hours=3,
            total_course_hours=30,
            subject_type="Practical",
            session_length=2,
        )
        legacy = Timetable(
            institute_id=institute_id,
            institute_code="TEST01",
            class_id="C1",
            day_name="Mon",
            start_time="08:00 AM",
            end_time="08:45 AM",
            subject_name="Legacy",
            teacher_name="Teacher",
        )
        db.session.add_all([subject, legacy])
        db.session.commit()

        result = engine_generate_timetable("TEST01")

        assert not result["success"]
        assert result["diagnostics"]["reason_code"] == "INVALID_SUBJECT_REQUIREMENT"
        remaining = Timetable.query.filter_by(institute_code="TEST01").all()
        assert len(remaining) == 1
        assert remaining[0].subject_name == "Legacy"


def test_nondefault_settings_keep_full_practical_after_lunch(app):
    with app.app_context():
        institute_id = Institute.query.filter_by(institute_code="TEST01").one().id
        course = Course(
            institute_id=institute_id,
            institute_code="TEST01",
            class_id="C1",
            department="CS",
            semester=1,
            division="A",
        )
        teacher = Teacher(
            institute_id=institute_id,
            institute_code="TEST01",
            teacher_id="T1",
            name="Teacher",
            email="teacher@example.com",
            departments="CS",
            available_days="Tue",
            max_hours=2,
        )
        db.session.add_all([course, teacher])
        db.session.flush()
        db.session.add(
            Subject(
                institute_id=institute_id,
                institute_code="TEST01",
                subject_code="LAB",
                subject_name="Lab",
                class_id="C1",
                teacher_id="T1",
                teacher_id_fk=teacher.id,
                required_hours=2,
                total_course_hours=14,
                subject_type="Practical",
                session_length=2,
            )
        )
        settings = {
            "working_days": "Tue",
            "total_lectures": "3",
            "start_time": "10:00",
            "lecture_duration": "30",
            "break_time": "20",
            "lunch_after_lecture": "1",
            "weeks_per_semester": "7",
        }
        db.session.add_all(
            Settings(institute_code="TEST01", key=key, value=value)
            for key, value in settings.items()
        )
        db.session.commit()

        result = engine_generate_timetable("TEST01")

        assert result["success"]
        assert result["stats"]["required_periods"] == 2
        assert result["stats"]["scheduled_periods"] == 2
        rows = Timetable.query.filter_by(institute_code="TEST01").order_by(
            Timetable.start_time
        ).all()
        assert [(row.day_name, row.start_time) for row in rows] == [
            ("Tue", "10:50 AM"),
            ("Tue", "11:20 AM"),
        ]
