import pytest
from models import db, Teacher, TeacherLeave, Timetable, Subject, Course, Institute
from datetime import timedelta
from utils.helpers import get_local_date


def setup_test_data(app):
    inst_code = "TEST01"
    with app.app_context():
        # Clean up existing data for TEST01
        Institute.query.filter_by(institute_code=inst_code).delete()
        Course.query.filter_by(institute_code=inst_code).delete()
        Teacher.query.filter_by(institute_code=inst_code).delete()
        Subject.query.filter_by(institute_code=inst_code).delete()
        Timetable.query.filter_by(institute_code=inst_code).delete()
        TeacherLeave.query.filter_by(institute_code=inst_code).delete()
        db.session.commit()

        inst = Institute(
            institute_code=inst_code,
            name="Test Institute",
            admin_username="admin",
            admin_email="admin@test.com",
            admin_password="pass",
        )
        db.session.add(inst)

        c = Course(
            institute_code=inst_code, class_id="FY-A", department="CS", semester=1, division="A"
        )
        db.session.add(c)

        t1 = Teacher(
            institute_code=inst_code,
            teacher_id="T1",
            name="Alice",
            email="alice@test.com",
            departments="CS",
            available_days="Mon,Tue,Wed",
            max_hours=10,
        )
        t2 = Teacher(
            institute_code=inst_code,
            teacher_id="T2",
            name="Bob",
            email="bob@test.com",
            departments="CS",
            available_days="Mon,Tue,Wed",
            max_hours=10,
        )
        t3 = Teacher(
            institute_code=inst_code,
            teacher_id="T3",
            name="Charlie",
            email="charlie@test.com",
            departments="CS",
            available_days="Mon,Tue,Wed,Thu,Fri",
            max_hours=10,
        )
        db.session.add_all([t1, t2, t3])

        s1 = Subject(
            institute_code=inst_code,
            subject_code="S1",
            subject_name="Math",
            class_id="FY-A",
            teacher_id="T1",
            required_hours=4,
            subject_type="Theory",
        )
        s2 = Subject(
            institute_code=inst_code,
            subject_code="S2",
            subject_name="Physics",
            class_id="FY-A",
            teacher_id="T2",
            required_hours=4,
            subject_type="Theory",
        )
        db.session.add_all([s1, s2])

        today = get_local_date()
        target_date = today + timedelta(days=(0 - today.weekday()) % 7 or 7)

        # Add master timetable entry for Alice on Monday
        lec = Timetable(
            institute_code=inst_code,
            class_id="FY-A",
            day_name="Mon",
            start_time="09:00",
            end_time="10:00",
            subject_name="Math",
            teacher_name="Alice",
        )
        db.session.add(lec)
        db.session.commit()
        return inst_code, target_date


def test_leave_proxy_workflow(app, client):
    inst_code, target_date = setup_test_data(app)

    with app.app_context():
        # A. Approved leave on target_date (Mon)
        leave = TeacherLeave(
            institute_code=inst_code, teacher_id="T1", date=target_date, status="Pending"
        )
        db.session.add(leave)
        db.session.commit()

        from utils.leave_service import approve_leave, cancel_leave

        success, msg = approve_leave(leave.id)
        assert success

        # Verify proxy
        proxy_lec = Timetable.query.filter_by(
            institute_code=inst_code, specific_date=target_date
        ).first()
        assert proxy_lec is not None
        assert proxy_lec.teacher_name == "Bob"
        assert proxy_lec.leave_id == leave.id

        # E. Reject (let's create another leave and reject)
        leave2 = TeacherLeave(
            institute_code=inst_code, teacher_id="T2", date=target_date, status="Pending"
        )
        db.session.add(leave2)
        db.session.commit()
        leave2.status = "Rejected"
        db.session.commit()
        proxy_lec2 = Timetable.query.filter_by(institute_code=inst_code, leave_id=leave2.id).first()
        assert proxy_lec2 is None

        # B. Cancel Pending
        leave3 = TeacherLeave(
            institute_code=inst_code,
            teacher_id="T2",
            date=target_date + timedelta(days=1),
            status="Pending",
        )
        db.session.add(leave3)
        db.session.commit()
        success, msg = cancel_leave(leave3.id, "Admin")
        assert success
        assert leave3.status == "Cancelled"

        # C. Cancel Approved future
        # Change target_date of first leave to future so we can cancel it
        leave.date = target_date + timedelta(days=7)  # Future
        db.session.commit()

        success, msg = cancel_leave(leave.id, "Admin")
        assert success
        assert leave.status == "Cancelled"
        # Proxy row should be deleted
        assert Timetable.query.filter_by(leave_id=leave.id).count() == 0
        # Master timetable should remain unchanged
        assert Timetable.query.filter_by(institute_code=inst_code, specific_date=None).count() == 1

        # D. Re-approve Approved leave (should not duplicate)
        leave.status = "Pending"
        db.session.commit()
        approve_leave(leave.id)
        assert Timetable.query.filter_by(leave_id=leave.id).count() == 1
        approve_leave(leave.id)  # Should fail or do nothing
        assert Timetable.query.filter_by(leave_id=leave.id).count() == 1


def test_available_days_constraints(app, client):
    inst_code = "TEST01"
    with app.app_context():
        # F. Inject invalid assignment: independent validator reports hard violation
        from utils.scheduler.validator import TimetableValidator
        from utils.scheduler.core import SessionOccurrence, TimeSlot

        units = [
            SessionOccurrence(
                id="U1",
                subject_id=1,
                subject_name="Math",
                teacher_id="T1",
                target_classes=["FY-A"],
                duration=1,
                preferred_days=[],
                is_practical=False,
            )
        ]
        time_slots = [TimeSlot(day="Sat", idx=0, start_time="09:00", end_time="10:00")]
        units[0].assigned_slot = time_slots[0]

        teacher_available_days = {"T1": {"Mon", "Tue"}}
        is_valid, errors = TimetableValidator.audit(units, time_slots, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], teacher_available_days, {"T1": 40}, 2)
        assert not is_valid
        assert "Hard Constraint Violation" in errors[0]
        assert "is not available" in errors[0]

        # G. duration-2 practical
        units[0].duration = 2
        units[0].is_practical = True
        time_slots.append(TimeSlot(day="Sat", idx=1, start_time="10:00", end_time="11:00"))
        is_valid, errors = TimetableValidator.audit(units, time_slots, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], teacher_available_days, {"T1": 40}, 2)
        assert not is_valid


def test_leave_default_pending(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        leave = TeacherLeave(institute_code=inst_code, teacher_id="T1", date=target_date)
        db.session.add(leave)
        db.session.commit()
        assert leave.status == "Pending", f"Expected default Pending, got {leave.status}"
