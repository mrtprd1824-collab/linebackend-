# app/services/oa_checker.py
from datetime import datetime, timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from app.extensions import db

def check_single_oa_status(account):
    """
    ตรวจสอบสถานะของ LineAccount หนึ่งบัญชีและอัปเดตค่าใน object
    :param account: SQLAlchemy object ของ LineAccount
    :return: สถานะ (True ถ้าปกติ, False ถ้ามีปัญหา)
    """
    print(f"Checking OA: {account.name}...")
    is_currently_active = True
    status_message = "OK"

    try:
        # 1. ตรวจสอบก่อนว่ามี Token หรือไม่
        if not account.channel_access_token:
            raise ValueError("Channel Access Token is missing.")

        # 2. สร้าง LineBotApi instance
        line_bot_api = LineBotApi(account.channel_access_token)
        
        # 3. เรียก API เพื่อตรวจสอบ Token (ใช้ get_bot_info เพราะ verify_access_token อาจไม่มีในบางเวอร์ชัน)
        bot_info = line_bot_api.get_bot_info()
        # ถ้าไม่มี Exception เกิดขึ้น แสดงว่า Token ใช้งานได้
        
    except LineBotApiError as e:
        # 4. ถ้า Token ไม่ถูกต้อง, OA ถูกระงับ, หรือมีปัญหาอื่นๆ
        is_currently_active = False
        status_message = f"Error {e.status_code}: {e.error.message}"
        print(f"  -> FAILED: {status_message}")
    except Exception as e:
        # 5. ดักจับ Error อื่นๆ ที่ไม่คาดคิด (เช่น ไม่มี Token, network error)
        is_currently_active = False
        status_message = f"Unexpected Error: {str(e)}"
        print(f"  -> FAILED: {status_message}")

    # 6. อัปเดตข้อมูลลงใน object ของ account (ยังไม่ commit)
    account.is_active = is_currently_active
    account.last_check_status_message = status_message
    account.last_check_timestamp = datetime.now(timezone.utc)
    
    return is_currently_active