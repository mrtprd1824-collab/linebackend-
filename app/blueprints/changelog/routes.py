# app/blueprints/changelog/routes.py - เส้นทางจัดการบันทึกการเปลี่ยนแปลงของระบบ
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List

import bleach
import pytz
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from markupsafe import Markup

from . import bp
from .forms import ChangeLogForm
from app.extensions import db
from app.models import ChangeLog
from app.services.authz import admin_required
from app.services.s3 import upload_fileobj

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
ALLOWED_TAGS = [
    "br",
    "p",
    "strong",
    "em",
    "u",
    "a",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
    "span",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "span": ["class"],
}
THAI_MONTHS = [
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]
NEW_THRESHOLD = timedelta(days=7)


def _ensure_timezone(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return pytz.utc.localize(dt)
    return dt.astimezone(pytz.UTC)


def _format_thai_date(dt: datetime) -> str:
    dt_bkk = dt.astimezone(BANGKOK_TZ)
    year_th = dt_bkk.year + 543
    return f"{dt_bkk.day} {THAI_MONTHS[dt_bkk.month - 1]} {year_th}"


def _humanize_delta(dt: datetime) -> str:
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    delta = now - dt.astimezone(pytz.UTC)
    if delta.days >= 365:
        years = delta.days // 365
        return f"{years} ปีที่แล้ว"
    if delta.days >= 30:
        months = delta.days // 30
        return f"{months} เดือนที่แล้ว"
    if delta.days >= 1:
        return f"{delta.days} วันที่แล้ว"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} ชั่วโมงที่แล้ว"
    minutes = delta.seconds // 60
    if minutes >= 1:
        return f"{minutes} นาทีที่แล้ว"
    return "เมื่อสักครู่"


def _sanitize_body(raw_body: str) -> Markup:
    html_ready = raw_body.replace("\r\n", "\n").replace("\n", "<br>")
    cleaned = bleach.clean(html_ready, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    return Markup(cleaned)


def _decorate_entries(entries: List[ChangeLog]) -> List[Dict]:
    grouped: "OrderedDict[datetime.date, Dict]" = OrderedDict()
    for entry in entries:
        created_at = entry.created_at or entry.updated_at or datetime.utcnow().replace(tzinfo=pytz.UTC)
        created_at = _ensure_timezone(created_at).astimezone(BANGKOK_TZ)
        date_key = created_at.date()

        if date_key not in grouped:
            grouped[date_key] = {
                "date_label": _format_thai_date(created_at),
                "relative": _humanize_delta(created_at),
                "entries": [],
            }

        is_new = (datetime.now(BANGKOK_TZ) - created_at) <= NEW_THRESHOLD

        grouped[date_key]["entries"].append(
            {
                "id": entry.id,
                "title": entry.title,
                "body_html": _sanitize_body(entry.body),
                "image_url": entry.image_url,
                "created_at": created_at,
                "updated_at": entry.updated_at,
                "is_new": is_new,
                "author_id": entry.created_by_admin_id,
            }
        )

    return list(grouped.values())


@bp.get("/changelog")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    per_page = max(1, min(per_page, 20))

    pagination = ChangeLog.query.order_by(ChangeLog.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    decorated = _decorate_entries(pagination.items)

    return render_template(
        "changelog/index.html",
        grouped_logs=decorated,
        pagination=pagination,
        now_bkk=datetime.now(BANGKOK_TZ),
    )


@bp.get("/changelog/<int:log_id>")
def detail(log_id: int):
    changelog = ChangeLog.query.get_or_404(log_id)
    decorated = _decorate_entries([changelog])[0]["items"][0]
    return render_template("changelog/detail.html", changelog=decorated)


@bp.get("/admin/changelog/new")
@admin_required
def new():
    form = ChangeLogForm()
    return render_template("changelog/form.html", form=form, form_action=url_for("changelog_bp.create"))


@bp.post("/admin/changelog")
@admin_required
def create():
    form = ChangeLogForm()
    if not form.validate_on_submit():
        flash("กรอกข้อมูลไม่ครบถ้วน", "warning")
        return render_template("changelog/form.html", form=form, form_action=url_for("changelog_bp.create")), 400

    changelog = ChangeLog(
        title=form.title.data.strip(),
        body=form.body.data.strip(),
        image_url=form.image_url.data.strip() if form.image_url.data else None,
        created_by_admin_id=current_user.id,
    )
    db.session.add(changelog)
    db.session.commit()
    flash("บันทึกการเปลี่ยนแปลงถูกสร้างแล้ว", "success")
    return redirect(url_for("changelog_bp.index"))


@bp.get("/admin/changelog/<int:log_id>/edit")
@admin_required
def edit(log_id: int):
    changelog = ChangeLog.query.get_or_404(log_id)
    form = ChangeLogForm(obj=changelog)
    return render_template(
        "changelog/form.html",
        form=form,
        form_action=url_for("changelog_bp.update", log_id=log_id),
        editing=True,
        changelog=changelog,
    )


@bp.post("/admin/changelog/<int:log_id>/update")
@admin_required
def update(log_id: int):
    changelog = ChangeLog.query.get_or_404(log_id)
    form = ChangeLogForm()
    if not form.validate_on_submit():
        flash("กรอกข้อมูลไม่ครบถ้วน", "warning")
        return (
            render_template(
                "changelog/form.html",
                form=form,
                form_action=url_for("changelog_bp.update", log_id=log_id),
                editing=True,
                changelog=changelog,
            ),
            400,
        )

    changelog.title = form.title.data.strip()
    changelog.body = form.body.data.strip()
    changelog.image_url = form.image_url.data.strip() if form.image_url.data else None
    db.session.commit()
    flash("อัปเดตบันทึกการเปลี่ยนแปลงแล้ว", "success")
    return redirect(url_for("changelog_bp.index"))


@bp.post("/admin/changelog/<int:log_id>/delete")
@admin_required
def delete(log_id: int):
    changelog = ChangeLog.query.get_or_404(log_id)
    db.session.delete(changelog)
    db.session.commit()
    flash("ลบบันทึกการเปลี่ยนแปลงเรียบร้อยแล้ว", "success")
    return redirect(url_for("changelog_bp.index"))


@bp.post("/admin/changelog/upload")
@admin_required
def upload():
    if "file" not in request.files:
        abort(400, description="Missing file")
    file = request.files["file"]

    try:
        url = upload_fileobj(file)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("Failed to upload changelog asset")
        return jsonify({"error": str(exc)}), 400

    return jsonify({"url": url}), 201
