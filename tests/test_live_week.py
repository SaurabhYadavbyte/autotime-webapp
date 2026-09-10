import pytest
from datetime import date, timedelta
from utils.timetable_adapter import get_live_week_timetable
from models import Timetable, Teacher, TeacherLeave, db, Notification
from utils.helpers import get_local_date
from utils.leave_service import cancel_leave

def test_a_current_week_auto_resolution(app):
    """
    Test A — Current week auto resolution
    """
    with app.app_context():
        ref_date = date(2026, 9, 2)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date)
        assert live_week["day_dates"]["Mon"] == date(2026, 8, 31)
        assert live_week["day_dates"]["Wed"] == date(2026, 9, 2)
        assert live_week["day_dates"]["Sat"] == date(2026, 9, 5)

def test_b_student_automatically_sees_proxy(app):
    """
    Test B — Student automatically sees proxy
    """
    with app.app_context():
        t_master = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher A", is_proxy=False)
        db.session.add(t_master)
        t_override = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher B", is_proxy=True, specific_date=date(2026, 9, 2))
        db.session.add(t_override)
        db.session.commit()

        ref_date = date(2026, 9, 2)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        records = live_week["records"]
        assert len(records) == 1
        assert records[0].teacher_name == "Teacher B"
        assert records[0].is_proxy == True

def test_c_teacher_filter_regression(app):
    """
    Test C — Teacher Filter Regression
    Creates Master Teacher A, Override Teacher B.
    Asserts resolving effective state THEN filtering by teacher.
    """
    with app.app_context():
        t_master = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher A", is_proxy=False)
        db.session.add(t_master)
        t_override = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher B", is_proxy=True, specific_date=date(2026, 9, 2))
        db.session.add(t_override)
        db.session.commit()

        ref_date = date(2026, 9, 2)

        # Test Teacher A (Original teacher removed from effective responsibility)
        live_week_a = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"teacher_name": "Teacher A"})
        assert len(live_week_a["records"]) == 0

        # Test Teacher B (Proxy teacher sees session)
        live_week_b = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"teacher_name": "Teacher B"})
        assert len(live_week_b["records"]) == 1
        assert live_week_b["records"][0].subject_name == "DBMS"
        assert live_week_b["records"][0].class_id == "FYCS-A"
        assert live_week_b["records"][0].is_proxy == True

def test_d_other_days_unchanged(app):
    """
    Test D — Other days unchanged
    """
    with app.app_context():
        # Wednesday Proxy setup
        t_wed_master = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher A", is_proxy=False)
        t_wed_override = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher B", is_proxy=True, specific_date=date(2026, 9, 2))
        # Monday Master setup (No override)
        t_monday = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Mon", start_time="10:00 AM", end_time="11:00 AM", subject_name="OS", teacher_name="Teacher A", is_proxy=False)
        db.session.add_all([t_wed_master, t_wed_override, t_monday])
        db.session.commit()

        ref_date = date(2026, 9, 2)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        records = live_week["records"]
        assert len(records) == 2

        mon_record = next(r for r in records if r.day_name == "Mon")
        assert mon_record.teacher_name == "Teacher A"
        assert mon_record.is_proxy == False

def test_e_real_revoke_integration(app):
    """
    Test E — Real Revoke Integration
    """
    with app.app_context():
        today = get_local_date()
        ref_date = today + timedelta(days=(2 - today.weekday()) % 7 or 7)

        # 1. Setup Master
        t_master = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher A", is_proxy=False)

        # Teacher details required for notifications
        teacher_a = Teacher(institute_code="TEST01", teacher_id="T01", name="Teacher A", email="a@test.com", departments="CS", available_days="Mon,Tue,Wed,Thu,Fri,Sat", max_hours=10)
        teacher_b = Teacher(institute_code="TEST01", teacher_id="T02", name="Teacher B", email="b@test.com", departments="CS", available_days="Mon,Tue,Wed,Thu,Fri,Sat", max_hours=10)

        # 2. Approved leave for Teacher A
        leave = TeacherLeave(institute_code="TEST01", teacher_id="T01", date=ref_date, status="Approved")
        db.session.add_all([t_master, teacher_a, teacher_b, leave])
        db.session.commit()

        # 3. Proxy linked to leave
        t_override = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Wed", start_time="10:00 AM", end_time="11:00 AM", subject_name="DBMS", teacher_name="Teacher B", is_proxy=True, specific_date=ref_date, leave_id=leave.id)
        db.session.add(t_override)
        db.session.commit()

        # Verify Live Week BEFORE revoke
        live_week_before = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        wed_record_before = next(r for r in live_week_before["records"] if r.day_name == "Wed")
        assert wed_record_before.teacher_name == "Teacher B"

        # 4. CALL REAL REVOKE
        # Notice we are cancelling the leave via the actual service
        success, msg = cancel_leave(leave.id, actor_name="Admin", institute_code="TEST01")
        assert success == True

        # Assert leave status
        assert leave.status == "Cancelled"

        # Assert leave-linked overrides removed
        proxy_count = Timetable.query.filter_by(leave_id=leave.id).count()
        assert proxy_count == 0

        # Assert Live Week automatically returns Teacher A
        live_week_after = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        wed_record_after = next(r for r in live_week_after["records"] if r.day_name == "Wed")
        assert wed_record_after.teacher_name == "Teacher A"
        assert wed_record_after.is_proxy == False

        # Assert Notifications were generated
        notifications = Notification.query.filter_by(institute_code="TEST01").all()
        assert len(notifications) > 0

def test_f_uncovered(app):
    """
    Test F — Uncovered
    """
    with app.app_context():
        t_uncovered = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Mon", start_time="10:00 AM", end_time="11:00 AM", subject_name="OS", teacher_name="__UNCOVERED__", is_proxy=True, specific_date=date(2026, 8, 31))
        db.session.add(t_uncovered)
        db.session.commit()

        ref_date = date(2026, 9, 2)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        records = live_week["records"]

        mon_record = next(r for r in records if r.day_name == "Mon")
        assert mon_record.teacher_name == "Teacher on Leave / Proxy Not Assigned"

        live_week_a = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"teacher_name": "Teacher A"})
        assert not any(r.day_name == "Mon" for r in live_week_a["records"])

def test_g_configurable_working_days(app):
    """
    Test G — Configurable working days
    """
    with app.app_context():
        from models import Settings
        s = Settings(institute_code="TEST01", key="working_days", value="Mon,Tue,Thu,Fri")
        db.session.add(s)
        db.session.commit()

        ref_date = date(2026, 9, 2)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date)

        assert "Mon" in live_week["working_days"]
        assert "Tue" in live_week["working_days"]
        assert "Wed" not in live_week["working_days"]
        assert "Sat" not in live_week["working_days"]

def test_h_shared_common_session(app):
    """
    Test H — Shared/common session
    """
    with app.app_context():
        # FYCS-A and FYCS-B share Teacher C for Math on Tue 11:00 AM
        m_a = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Tue", start_time="11:00 AM", end_time="12:00 PM", subject_name="Math", teacher_name="Teacher C", session_group_id="S1")
        m_b = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Tue", start_time="11:00 AM", end_time="12:00 PM", subject_name="Math", teacher_name="Teacher C", session_group_id="S1")

        # Override applies to both classes with same specific_date and session_group_id
        o_a = Timetable(institute_code="TEST01", class_id="FYCS-A", day_name="Tue", start_time="11:00 AM", end_time="12:00 PM", subject_name="Math", teacher_name="Teacher D", is_proxy=True, specific_date=date(2026, 9, 1), session_group_id="S1")
        o_b = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Tue", start_time="11:00 AM", end_time="12:00 PM", subject_name="Math", teacher_name="Teacher D", is_proxy=True, specific_date=date(2026, 9, 1), session_group_id="S1")
        db.session.add_all([m_a, m_b, o_a, o_b])
        db.session.commit()

        ref_date = date(2026, 9, 1)

        # Request separately
        live_week_a = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-A"})
        r_a = next(r for r in live_week_a["records"] if r.day_name == "Tue" and r.start_time == "11:00 AM")

        live_week_b = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-B"})
        r_b = next(r for r in live_week_b["records"] if r.day_name == "Tue" and r.start_time == "11:00 AM")

        assert r_a.teacher_name == "Teacher D"
        assert r_b.teacher_name == "Teacher D"
        assert r_a.specific_date == date(2026, 9, 1)
        assert r_b.specific_date == date(2026, 9, 1)
        assert r_a.session_group_id == "S1"
        assert r_b.session_group_id == "S1"

def test_i_practical_block(app):
    """
    Test I — Practical block
    """
    with app.app_context():
        m1 = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Thu", start_time="1:00 PM", end_time="1:45 PM", subject_name="Lab", teacher_name="Teacher C", session_group_id="P1")
        m2 = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Thu", start_time="1:45 PM", end_time="2:30 PM", subject_name="Lab", teacher_name="Teacher C", session_group_id="P1")

        o1 = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Thu", start_time="1:00 PM", end_time="1:45 PM", subject_name="Lab", teacher_name="Teacher D", is_proxy=True, specific_date=date(2026, 9, 3))
        o2 = Timetable(institute_code="TEST01", class_id="FYCS-B", day_name="Thu", start_time="1:45 PM", end_time="2:30 PM", subject_name="Lab", teacher_name="Teacher D", is_proxy=True, specific_date=date(2026, 9, 3))

        db.session.add_all([m1, m2, o1, o2])
        db.session.commit()

        ref_date = date(2026, 9, 3)
        live_week = get_live_week_timetable("TEST01", reference_date=ref_date, filters={"class_id": "FYCS-B"})

        r1 = next(r for r in live_week["records"] if r.start_time == "1:00 PM")
        r2 = next(r for r in live_week["records"] if r.start_time == "1:45 PM")

        assert r1.teacher_name == "Teacher D"
        assert r2.teacher_name == "Teacher D"
