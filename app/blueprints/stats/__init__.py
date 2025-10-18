# app/blueprints/stats/__init__.py - ติดตั้ง Blueprint สำหรับหน้าสถิติ
from flask import Blueprint

bp = Blueprint("stats", __name__, url_prefix="/stats")

from . import routes  # noqa: E402,F401
