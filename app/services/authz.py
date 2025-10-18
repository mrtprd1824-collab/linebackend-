# app/services/authz.py - ตัวช่วยตรวจสอบสิทธิ์การเข้าถึงของผู้ใช้
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask import flash, redirect, url_for
from flask_login import current_user, login_required

F = TypeVar("F", bound=Callable[..., Any])


def is_admin() -> bool:
    """เช็คว่า current_user เป็น admin หรือไม่"""
    if not current_user.is_authenticated:
        return False
    if hasattr(current_user, "is_admin"):
        try:
            return bool(current_user.is_admin)
        except TypeError:
            return bool(current_user.is_admin())
    return bool(getattr(current_user, "role", "").lower() == "admin")


def admin_required(func: F) -> F:
    """Decorator บังคับสิทธิ์ admin พร้อม redirect หากไม่ผ่าน"""

    @wraps(func)
    @login_required
    def wrapped(*args: Any, **kwargs: Any):
        if not is_admin():
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("auth.dashboard"))
        return func(*args, **kwargs)

    return wrapped  # type: ignore[return-value]
