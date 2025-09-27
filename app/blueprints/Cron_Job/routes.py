# ในไฟล์ routes ของคุณ (เช่น app/routes/api.py)

import os
from flask import Blueprint, request, jsonify
from app.models import LineAccount # <-- Import Model ของคุณ
from app.services.oa_checker import check_single_oa_status # <-- Import ฟังก์ชันที่คุณมี
from app.extensions import db

# สร้าง Blueprint สำหรับ cron jobs
cron_bp = Blueprint('cron', __name__, url_prefix='/api/cron')

@cron_bp.route('/check-all-oa-status', methods=['POST'])
def trigger_oa_health_check():
    # 1. (แนะนำ) เพิ่มการตรวจสอบความปลอดภัย
    # ให้แน่ใจว่า Request นี้มาจาก Render Cron Job จริงๆ ไม่ใช่ใครก็ได้
    cron_secret = os.environ.get('CRON_SECRET')
    auth_header = request.headers.get('Authorization')

    if not cron_secret or auth_header != f"Bearer {cron_secret}":
        print("Unauthorized cron job attempt.")
        return jsonify({"error": "Unauthorized"}), 401

    print("Cron job triggered: Starting OA health check for all accounts...")
    
    try:
        # 2. ดึงรายชื่อ OA ทั้งหมดที่ต้องการตรวจสอบจากฐานข้อมูล
        accounts_to_check = LineAccount.query.all()
        
        if not accounts_to_check:
            print("No accounts found to check.")
            return jsonify({"message": "No accounts to check."}), 200

        # 3. วนลูปเพื่อตรวจสอบสถานะทีละบัญชี
        for account in accounts_to_check:
            check_single_oa_status(account) # <-- เรียกใช้ฟังก์ชันที่คุณมี
            # ฟังก์ชันนี้จะอัปเดตข้อมูลใน object แต่ยังไม่ save ลง db
        
        # 4. เมื่อตรวจสอบครบทั้งหมดแล้ว ให้ commit การเปลี่ยนแปลงทั้งหมดลง DB ในครั้งเดียว
        db.session.commit()
        
        print(f"Cron job finished: Successfully checked and updated {len(accounts_to_check)} accounts.")
        return jsonify({"message": f"Successfully checked {len(accounts_to_check)} accounts."}), 200

    except Exception as e:
        db.session.rollback() # ถ้ามีปัญหา ให้ยกเลิกการเปลี่ยนแปลงทั้งหมด
        print(f"An error occurred during the cron job: {str(e)}")
        return jsonify({"error": "An internal error occurred."}), 500

# อย่าลืมลงทะเบียน Blueprint นี้ในไฟล์ __init__.py ของแอปพลิเคชัน
# from .routes.api import cron_bp
# app.register_blueprint(cron_bp)