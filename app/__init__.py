# app/__init__.py
import os
from flask import Flask, redirect, url_for
from flask_login import current_user
from config import Config
from .extensions import db, migrate, login_manager, socketio  # รวมบรรทัดเดียว

def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
    )

    # โหลดคอนฟิกครั้งเดียว
    app.config.from_object(Config)

    # init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(app, async_mode="eventlet")

    # ให้ Alembic เห็น models
    from . import models

    # import และ register blueprints (import ข้างในกันวงกลม)
    from .blueprints.auth.routes import bp as auth_bp
    from .blueprints.admin.routes import bp as admin_bp
    from .blueprints.line_admin import bp as line_admin_bp
    from .blueprints.line_webhook import bp as line_webhook_bp
    from .blueprints.chats import bp as chats_bp
    from .blueprints.quick_replies.routes import bp as quick_replies_bp
    from .blueprints.oa_groups.routes import bp as oa_groups_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(line_admin_bp)
    app.register_blueprint(line_webhook_bp)
    app.register_blueprint(chats_bp)  # ถ้า bp ตั้ง url_prefix ในไฟล์อยู่แล้ว ไม่ต้องใส่ซ้ำตรงนี้
    app.register_blueprint(quick_replies_bp)
    app.register_blueprint(oa_groups_bp)

    @app.get("/_env_check")
    def _env_check():
        import os
        def mask(v): 
            return (v[:4] + "..." + v[-3:]) if v and len(v) > 8 else v

        return {
            "REGION": app.config.get("AWS_DEFAULT_REGION"),
            "BUCKET": app.config.get("S3_BUCKET_NAME"),
            "PREFIX": app.config.get("S3_PREFIX"),
            "KEY_ID": mask(os.environ.get("AWS_ACCESS_KEY_ID")),
    }

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("auth.dashboard"))
        return redirect(url_for("auth.login"))

    return app
