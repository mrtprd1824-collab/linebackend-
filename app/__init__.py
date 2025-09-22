import os
from flask import Flask, redirect, url_for
from flask_login import current_user
from .extensions import db, migrate, login_manager
from .blueprints.auth.routes import bp as auth_bp
from .blueprints.admin.routes import bp as admin_bp
from .blueprints.line_admin import bp as line_admin_bp
from app.blueprints.line_webhook import bp as line_webhook_bp
from config import Config
from app.blueprints.chats import bp as chats_bp
from .blueprints.quick_replies.routes import bp as quick_replies_bp
from .blueprints.oa_groups.routes import bp as oa_groups_bp
from .extensions import db, login_manager, socketio
from flask_migrate import Migrate


def create_app():

    app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static")
    )

    # ✅ โหลดค่าจาก config.py ก่อน
    app.config.from_object(Config)

    # ✅ init extensions หลังจาก config พร้อมแล้ว
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # ✅ import models เพื่อให้ migrations เห็น
    from . import models
    from app.blueprints.line_webhook import bp as line_webhook_bp

    # ✅ register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(line_admin_bp)
    app.register_blueprint(line_webhook_bp)
    app.register_blueprint(chats_bp, url_prefix='/chats')
    app.register_blueprint(quick_replies_bp)
    app.register_blueprint(oa_groups_bp)
    socketio.init_app(app)


    # ✅ route หลัก
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("auth.dashboard"))
        else:
            return redirect(url_for("auth.login"))

    return app
