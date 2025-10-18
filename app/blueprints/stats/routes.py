# app/blueprints/stats/routes.py - จัดการหน้าและ API ของสถิติการใช้งาน
from flask import jsonify, render_template, request
from flask_login import login_required

from . import bp
from app.services.stats_service import fetch_by_admin, fetch_by_oa, fetch_summary

TZ_NAME = "Asia/Bangkok"


def _range_payload(range_pair):
    """จัดรูปแบบช่วงเวลาที่ใช้ตอบกลับ API"""
    start_bkk, end_bkk = range_pair
    return {
        "start": start_bkk.isoformat(),
        "end": end_bkk.isoformat(),
        "tz": TZ_NAME,
    }


@bp.get("/")
@login_required
def index():
    """เรนเดอร์หน้า HTML สำหรับดูสถิติ"""
    return render_template("stats/index.html")


@bp.get("/api/summary")
@login_required
def api_summary():
    """API สรุป KPI หลักของช่วงเวลาที่ร้องขอ"""
    oa_id = request.args.get("oa_id", type=int)
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    try:
        kpis, range_pair = fetch_summary(oa_id, start_raw, end_raw)
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    return jsonify(
        {
            "range": _range_payload(range_pair),
            "scope": {"oa_id": oa_id},
            "kpis": kpis,
        }
    )


@bp.get("/api/by-oa")
@login_required
def api_by_oa():
    """API แสดงอันดับตามแต่ละ OA"""
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    try:
        rows, _ = fetch_by_oa(start_raw, end_raw)
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    return jsonify(rows)


@bp.get("/api/by-admin")
@login_required
def api_by_admin():
    """API แสดงอันดับตามแอดมิน"""
    oa_id = request.args.get("oa_id", type=int)
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    try:
        rows, _ = fetch_by_admin(oa_id, start_raw, end_raw)
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    return jsonify(rows)
