import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify

from models import db
from routes.blueprint import main_bp
from utils.security import configure_security

import routes.auth
import routes.admin
import routes.student
import routes.teacher


def _environment_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    secret_key = (test_config or {}).get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("No SECRET_KEY set for Flask application")

    app.config.update(
        SECRET_KEY=secret_key,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_environment_flag(
            "SESSION_COOKIE_SECURE", default=_environment_flag("VERCEL")
        ),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    if test_config is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///autotime.db")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url
        app.config["AUTO_CREATE_SCHEMA"] = _environment_flag(
            "AUTO_CREATE_SCHEMA", default=True
        )
    else:
        app.config.update(test_config)

    db.init_app(app)
    configure_security(app)

    if app.config.get("AUTO_CREATE_SCHEMA", False):
        with app.app_context():
            try:
                db.create_all()
            except Exception as e:
                print(f"Error creating schema: {e}")


    app.register_blueprint(main_bp)

    @app.get("/healthz")
    def health_check():
        return jsonify(status="ok")

    @app.errorhandler(413)
    def request_too_large(_error):
        return "Uploaded file is too large. Maximum size is 5 MB.", 413

    @app.context_processor
    def inject_template_globals():
        from flask import session
        from models import Notification
        unread_count = 0
        if "institute_code" in session:
            inst_code = session["institute_code"]
            if "admin_id" in session:
                unread_count = Notification.query.filter_by(
                    institute_code=inst_code, user_type="admin", is_read=False
                ).count()
            elif "teacher_id" in session:
                unread_count = Notification.query.filter_by(
                    institute_code=inst_code, user_type="teacher", user_id=session["teacher_id"], is_read=False
                ).count()
            elif "student_id" in session:
                # Assuming students might get notifications in the future, currently we don't have student notifications
                # But to prevent error we set it to 0
                unread_count = 0

        return {
            "current_year": datetime.now(ZoneInfo("Asia/Kolkata")).year,
            "unread_notification_count": unread_count
        }

    @app.template_filter("ist_datetime")
    def format_ist_datetime(value):
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        ist_time = value.astimezone(ZoneInfo("Asia/Kolkata"))
        return ist_time.strftime("%d %b %Y, %I:%M %p")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=_environment_flag("FLASK_DEBUG"))
