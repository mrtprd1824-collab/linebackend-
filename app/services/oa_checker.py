# app/services/oa_checker.py
from datetime import datetime, timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from app.extensions import db
import requests
import os

def check_single_oa_status(account):
    """
    ตรวจสอบสถานะ Token และคืนค่าเป็น (is_ok: bool, message: str)
    ฟังก์ชันนี้จะไม่แก้ไข object account อีกต่อไป
    """
    print(f"Checking OA Status for: {account.name}...")
    
    try:
        if not account.channel_access_token:
            raise ValueError("Channel Access Token is missing.")

        line_bot_api = LineBotApi(account.channel_access_token, timeout=10)
        line_bot_api.get_bot_info()
        
        # ถ้าสำเร็จ คืนค่า True และ "OK"
        return True, "OK"
        
    except LineBotApiError as e:
        message = f"Error {e.status_code}: {e.error.message}"
        print(f"  -> FAILED with LineBotApiError: {message}")
        return False, message
    except Exception as e:
        message = f"Unexpected Error: {str(e)}"
        print(f"  -> FAILED with Exception: {message}")
        return False, message



def check_single_oa_webhook(account):
    """
    ตรวจสอบ Webhook และคืนค่าเป็น (is_ok: bool, message: str)
    ฟังก์ชันนี้จะไม่แก้ไข object account อีกต่อไป
    """
    print(f"Checking OA Webhook for: {account.name} (using requests)...")
    
    APP_BASE_URL = os.environ.get('APP_BASE_URL')
    if not APP_BASE_URL:
        return False, "Config Error: APP_BASE_URL not set"
    
    path = account.webhook_path
    if not path:
        return False, "Config Error: webhook_path is empty"

    CORRECT_WEBHOOK_URL = f"{APP_BASE_URL}/{path}/callback"
    
    headers = {'Authorization': f'Bearer {account.channel_access_token}'}
    line_api_url = 'https://api.line.me/v2/bot/channel/webhook/endpoint'

    try:
        response = requests.get(line_api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            webhook_info = response.json()
            configured_url = webhook_info.get('endpoint')
            is_enabled = webhook_info.get('active', False)

            if not is_enabled:
                return False, "Webhook is disabled"
            elif configured_url != CORRECT_WEBHOOK_URL:
                return False, "URL Mismatch"
            else:
                return True, "OK"
                
        elif response.status_code == 404:
            return False, "Webhook Not Set"
        else:
            error_details = response.json().get('message', 'Unknown API Error')
            return False, f"API Error {response.status_code}: {error_details}"

    except requests.exceptions.RequestException as e:
        return False, f"Network Error: {type(e).__name__}"
