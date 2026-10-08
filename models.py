from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
from datetime import datetime, timezone


def utc_now():
    """Return naive UTC for compatibility with the existing database schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================
# DATABASE MODELS
# ==========================================


class SubjectCourse(db.Model):
    __tablename__ = "subject_courses"
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), primary_key=True
    )
    is_active = db.Column(db.Boolean, default=True)


class Institute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    institute_code = db.Column(db.String(20), unique=True, nullable=False)
    admin_username = db.Column(db.String(50), unique=True, nullable=False)
    admin_email = db.Column(db.String(100), unique=True, nullable=False)
    admin_password = db.Column(db.String(255), nullable=False)


class Teacher(db.Model):
    __table_args__ = (
        db.UniqueConstraint("institute_code", "teacher_id", name="uq_teacher_institute_identifier"),
        db.Index("ix_teacher_institute_name", "institute_code", "name"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(
        db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True
    )
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    departments = db.Column(db.String(100), nullable=False)
    subjects = db.Column(db.String(500), nullable=True)
    available_days = db.Column(db.String(100), nullable=False)
    max_hours = db.Column(db.Integer, nullable=False)
    password = db.Column(db.String(255), nullable=True)


class Course(db.Model):
    __table_args__ = (
        db.UniqueConstraint("institute_code", "class_id", name="uq_course_institute_class"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(
        db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True
    )
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    division = db.Column(db.String(10), nullable=False)


class Subject(db.Model):
    __table_args__ = (
        db.UniqueConstraint("institute_code", "subject_code", name="uq_subject_institute_code"),
        db.Index("ix_subject_institute_teacher", "institute_code", "teacher_id"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(
        db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True
    )
    teacher_id_fk = db.Column(
        db.Integer, db.ForeignKey("teacher.id", ondelete="RESTRICT"), nullable=True
    )
    courses = db.relationship(
        "Course", secondary="subject_courses", backref=db.backref("subjects", lazy="dynamic")
    )
    institute_code = db.Column(db.String(20), nullable=False)
    subject_code = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    total_course_hours = db.Column(db.Integer, nullable=False, default=50)
    required_hours = db.Column(db.Integer, nullable=False)  # Weekly
    completed_hours = db.Column(db.Integer, nullable=False, default=0)  # Syllabus tracker
    subject_type = db.Column(db.String(50), default="Theory")
    session_length = db.Column(db.Integer, default=1)
    preferred_days = db.Column(db.String(100), default="")


class Timetable(db.Model):
    __table_args__ = (
        db.Index(
            "ix_timetable_institute_class_slot",
            "institute_code",
            "class_id",
            "day_name",
            "start_time",
        ),
        db.Index(
            "ix_timetable_institute_teacher_slot",
            "institute_code",
            "teacher_name",
            "day_name",
            "start_time",
        ),
        db.Index("ix_timetable_institute_date", "institute_code", "specific_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(
        db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True
    )
    course_id_fk = db.Column(
        db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=True
    )
    teacher_id_fk = db.Column(
        db.Integer, db.ForeignKey("teacher.id", ondelete="CASCADE"), nullable=True
    )
    subject_id_fk = db.Column(
        db.Integer, db.ForeignKey("subject.id", ondelete="CASCADE"), nullable=True
    )
    session_group_id = db.Column(db.String(50), nullable=True, index=True)
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    day_name = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    teacher_name = db.Column(db.String(100), nullable=False)
    is_proxy = db.Column(db.Boolean, default=False)
    specific_date = db.Column(
        db.Date, nullable=True
    )  # Used for Make-Up/Proxy classes assigned to a specific date
    leave_id = db.Column(
        db.Integer, db.ForeignKey("teacher_leave.id"), nullable=True
    )  # Traceability to originating leave assigned to a specific date


class Settings(db.Model):
    __table_args__ = (
        db.UniqueConstraint("institute_code", "key", name="uq_settings_institute_key"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(100), nullable=False)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)


class TeacherUpdateRequest(db.Model):
    __table_args__ = (db.Index("ix_update_request_institute_status", "institute_code", "status"),)
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    new_name = db.Column(db.String(100), nullable=True)
    new_email = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default="Pending")
    created_at = db.Column(db.DateTime, default=utc_now)


class AcademicCalendar(db.Model):
    __table_args__ = (db.Index("ix_calendar_institute_date", "institute_code", "date"),)
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    event_name = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(50), nullable=True)  # All, or specific dept
    is_holiday = db.Column(db.Boolean, default=True)  # If true, regular lectures are hidden


class TeacherLeave(db.Model):
    __table_args__ = (
        db.Index("ix_leave_institute_status_date", "institute_code", "status", "date"),
        db.Index("ix_leave_teacher_date", "institute_code", "teacher_id", "date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(20), nullable=True)  # Used for specific-period leave
    status = db.Column(db.String(20), default="Pending")  # Pending, Approved, Rejected


class Notification(db.Model):
    __table_args__ = (
        db.Index(
            "ix_notification_recipient", "institute_code", "user_type", "user_id", "created_at"
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # 'admin' or 'teacher'
    user_id = db.Column(db.String(50), nullable=True)  # teacher_id, or None for admin
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utc_now)


class GenerationHistory(db.Model):
    __tablename__ = "generation_history"
    __table_args__ = (
        db.Index("ix_generation_history_institute_created", "institute_code", "created_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(
        db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=False
    )
    institute_code = db.Column(
        db.String(20), nullable=False
    )  # Kept as legacy/user-facing identifier
    status = db.Column(db.String(20), nullable=False)  # SUCCESS, FAILED
    sessions_count = db.Column(db.Integer, nullable=False, default=0)
    generation_time = db.Column(db.Float, nullable=True)
    optimization_time = db.Column(db.Float, nullable=True)
    gap_score = db.Column(db.Integer, nullable=True)
    primary_failure_reason = db.Column(db.String(255), nullable=True)
    diagnostics_json = db.Column(
        db.Text, nullable=True
    )  # Optional JSON payload for detailed UI if needed
    created_at = db.Column(db.DateTime, default=utc_now)
