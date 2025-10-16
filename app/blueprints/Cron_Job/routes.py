# app/blueprints/cron_job/routes.py
import os
from flask import Blueprint, request, jsonify
from app.models import LineAccount
from app.services.oa_checker import run_full_health_check  # ← ฟังก์ชัน SYNC
from app.extensions import db
# (ถ้ามีระบบ logging อยู่แล้ว แนะนำใช้ logger แทน print)

cron_bp = Blueprint("cron", __name__, url_prefix="/api/cron")

@cron_bp.route("/check-all-oa-status", methods=["POST"])
def trigger_oa_health_check():
    cron_secret = os.environ.get("CRON_SECRET")
    auth_header = request.headers.get("Authorization", "")

    # 503 เมื่อระบบยังไม่ได้ตั้งค่า CRON_SECRET ชัดเจน
    if not cron_secret:
        return jsonify({"error": "CRON_SECRET not configured"}), 503

    if auth_header != f"Bearer {cron_secret}":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        accounts = LineAccount.query.all()
        if not accounts:
            return jsonify({"message": "No accounts to check.", "checked": 0}), 200

        checked = 0
        errors = []

        for acc in accounts:
            try:
                # ✅ เรียก SYNC function (ไม่มี await)
                run_full_health_check(acc)
                checked += 1
            except Exception as e:
                # ไม่ให้ทั้งงานล่มเพราะบัญชีเดียวพัง
                errors.append({"id": acc.id, "name": getattr(acc, "name", None), "error": type(e).__name__})

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                "error": "CommitFailed",
                "details": str(e),
                "checked": checked,
                "partial_errors": errors
            }), 500

        return jsonify({"message": "OK", "checked": checked, "errors": errors}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "InternalError", "details": str(e)}), 500
