# app/services/oa_checker.py  (เวอร์ชัน SYNC)
from datetime import datetime, timezone
import os
import requests
from requests.adapters import HTTPAdapter, Retry
from app.extensions import db  # เผื่อในอนาคตใช้ commit ภายใน service (ตอนนี้ไม่จำเป็น)

def _requests_session(timeout=(5, 10)):
    """
    สร้าง Session ที่มี retry สำหรับ error เครือข่ายชั่วคราว
    timeout = (connect_timeout, read_timeout) หน่วยวินาที
    """
    sess = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "POST", "HEAD", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.request_timeout = timeout
    return sess

def check_single_oa_status(account):
    """
    ตรวจสอบสถานะ Token กับ LINE Messaging API (SYNC)
    คืนค่า: (is_ok: bool, message: str)
    """
    print(f"Checking OA Status for: {account.name}...")
    if not getattr(account, "channel_access_token", None):
        return False, "Channel Access Token is missing."

    headers = {"Authorization": f"Bearer {account.channel_access_token}"}
    api_url = "https://api.line.me/v2/bot/info"

    sess = _requests_session()
    try:
        resp = sess.get(api_url, headers=headers, timeout=sess.request_timeout)
        if resp.status_code == 200:
            return True, "OK"
        else:
            # ป้องกันกรณี body ไม่ใช่ JSON
            try:
                err = resp.json().get("message", "Unknown API Error")
            except Exception:
                err = resp.text[:200] if resp.text else "Unknown API Error"
            return False, f"API Error {resp.status_code}: {err}"
    except requests.RequestException as e:
        return False, f"Network Error: {type(e).__name__}"

def check_single_oa_webhook(account):
    """
    ตรวจสอบการตั้งค่า Webhook (SYNC)
    - ดึงค่า endpoint/active จาก LINE (ถ้า token มีสิทธิ์)
    - เทียบกับ URL ที่เราคาดหวังจาก APP_BASE_URL + webhook_path
    คืนค่า: (is_ok: bool, message: str)
    """
    print(f"Checking OA Webhook for: {account.name}...")
    APP_BASE_URL = os.environ.get("APP_BASE_URL")
    if not APP_BASE_URL:
        return False, "Config Error: APP_BASE_URL not set"

    path = getattr(account, "webhook_path", None)
    if not path:
        return False, "Config Error: webhook_path is empty"

    CORRECT_WEBHOOK_URL = f"{APP_BASE_URL}/{path}/callback"
    headers = {"Authorization": f"Bearer {account.channel_access_token}"}
    line_api_url = "https://api.line.me/v2/bot/channel/webhook/endpoint"

    sess = _requests_session()
    try:
        resp = sess.get(line_api_url, headers=headers, timeout=sess.request_timeout)
        if resp.status_code == 200:
            # ตัวอย่างตามโค้ดเดิมของคุณ: คาดว่าได้ {"active": bool, "endpoint": "..."}
            try:
                webhook_info = resp.json()
            except Exception:
                return False, "Invalid JSON from LINE API"

            is_enabled = webhook_info.get("active", False)
            if not is_enabled:
                return False, "Webhook is disabled"

            configured_url = webhook_info.get("endpoint")
            if configured_url != CORRECT_WEBHOOK_URL:
                return False, "URL Mismatch"

            return True, "OK"

        elif resp.status_code == 404:
            # กรณี LINE แจ้งว่าไม่มีการตั้ง webhook
            return False, "Webhook Not Set"

        else:
            try:
                err = resp.json().get("message", "Unknown API Error")
            except Exception:
                err = resp.text[:200] if resp.text else "Unknown API Error"
            return False, f"API Error {resp.status_code}: {err}"

    except requests.RequestException as e:
        return False, f"Network Error: {type(e).__name__}"

def run_full_health_check(account):
    """
    ฟังก์ชันหลักสำหรับเรียกตรวจสอบ OA (SYNC) และอัปเดตข้อมูลลงใน object (แต่ไม่ commit)
    - รวมผล Token + Webhook
    - อัปเดต: is_active, last_check_status_message, last_check_timestamp
    """
    token_ok, token_msg = check_single_oa_status(account)
    webhook_ok, webhook_msg = check_single_oa_webhook(account)

    account.is_active = bool(token_ok and webhook_ok)

    status_parts = [f"Token: {token_msg}", f"Webhook: {webhook_msg}"]
    account.last_check_status_message = ", ".join(status_parts)

    account.last_check_timestamp = datetime.now(timezone.utc)

    print(
        f"  -> Health check for '{account.name}' completed. "
        f"Overall Status: {'Active' if account.is_active else 'Inactive'}"
    )
