# app/blueprints/changelog/__init__.py - Blueprint สำหรับหน้าบันทึกการเปลี่ยนแปลง
from flask import Blueprint

bp = Blueprint("changelog_bp", __name__, template_folder="../../templates", static_folder="../../static")

from . import routes  # noqa: E402,F401
