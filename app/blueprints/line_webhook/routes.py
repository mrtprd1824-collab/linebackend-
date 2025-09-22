from flask import request, current_app
from flask_socketio import join_room, leave_room
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from app.models import db, LineAccount, LineMessage, LineUser
from . import bp
import json
import os
from datetime import datetime

# [สำคัญ] เพิ่ม import ที่จำเป็น
from app.extensions import socketio
from flask_socketio import join_room, leave_room


@bp.route("/<string:webhook_path>/callback", methods=["POST"])
def callback(webhook_path):
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    
    line_account = LineAccount.query.filter_by(webhook_path=webhook_path).first()
    if not line_account:
        return "LineAccount not found", 404

    handler = WebhookHandler(line_account.channel_secret)
    line_bot_api = LineBotApi(line_account.channel_access_token)

    try:
        handler.handle(body, signature)
        data = json.loads(body)
        events = data.get("events", [])

        for event in events:
            user_id = event.get("source", {}).get("userId")
            if not user_id:
                continue

            # --- 1. ค้นหาหรือสร้าง LineUser ---
            line_user = LineUser.query.filter_by(
                line_account_id=line_account.id, user_id=user_id
            ).first()

            if not line_user:
                line_user = LineUser(line_account_id=line_account.id, user_id=user_id)
                db.session.add(line_user) # เพิ่ม user ใหม่เข้าไปใน session ก่อน
            
            # อัปเดต Profile (ถ้าทำได้)
            try:
                profile = line_bot_api.get_profile(user_id)
                line_user.display_name = profile.display_name
                line_user.picture_url = profile.picture_url
            except Exception as e:
                print(f"Could not get profile for {user_id}: {e}")

            # --- [แก้ไข] ย้ายการอัปเดตสถานะและเวลามาไว้ตรงนี้ ---
            line_user.status = 'unread'
            line_user.last_seen_at = datetime.utcnow()

            # --- 2. บันทึกข้อความที่เข้ามา (ถ้ามี) ---
            new_msg = None # 1. [เพิ่ม] กำหนดค่าเริ่มต้นให้ new_msg
            if event.get("type") == "message":
                msg_type = event["message"]["type"]

                if msg_type == "text":
                    new_msg = LineMessage(
                        line_account_id=line_account.id, user_id=user_id,
                        message_type="text", message_text=event["message"]["text"],
                        timestamp=datetime.utcnow(), is_outgoing=False
                    )

                elif msg_type == "image":
                    message_id = event["message"]["id"]
                    message_content = line_bot_api.get_message_content(message_id)
                    file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{message_id}.jpg"
                    save_path = os.path.join(
                        current_app.root_path, "..", "static", "uploads", file_name
                    )
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        for chunk in message_content.iter_content():
                            f.write(chunk)

                    new_msg = LineMessage(
                        line_account_id=line_account.id,
                        user_id=user_id,
                        message_type="image",
                        message_url=f"/static/uploads/{file_name}",
                        timestamp=datetime.utcnow()
                    )

                elif msg_type == "sticker":
                    new_msg = LineMessage(
                        line_account_id=line_account.id,
                        user_id=user_id,
                        message_type="sticker",
                        sticker_id=event["message"]["stickerId"],
                        package_id=event["message"]["packageId"],
                        timestamp=datetime.utcnow()
                    )

                else:
                    # message ประเภทอื่นยังไม่รองรับ
                    continue
                
                if new_msg:
                    db.session.add(new_msg)
                    db.session.commit()

                    content_for_socket = ""
                    if new_msg.message_type == 'text':
                        content_for_socket = new_msg.message_text
                    elif new_msg.message_type == 'image':
                        # สำหรับรูปภาพ ให้ใช้ message_url ที่เราบันทึกไว้
                        content_for_socket = new_msg.message_url
                    elif new_msg.message_type == 'sticker':
                        # สำหรับสติกเกอร์ ให้สร้าง URL เต็ม
                        content_for_socket = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{new_msg.sticker_id}/ANDROID/sticker.png"
                    
                    # --- 3. [แก้ไข] กระจายเสียง Event หลังจากสร้าง new_msg แล้ว ---
                    socketio.emit('new_message', {
                        'id': new_msg.id,
                        'sender_type': 'customer',
                        'message_type': new_msg.message_type,
                        'content': content_for_socket, # <--- ใช้ตัวแปรใหม่
                        'full_datetime': new_msg.timestamp.strftime('%d %b - %H:%M'),
                        'user_id': user_id,
                        'oa_id': line_account.id
                    }, to=f"chat_{user_id}_{line_account.id}")

                    socketio.emit('update_conversation_list', {
                        'user_id': user_id,
                        'line_account_id': line_account.id,
                        'display_name': line_user.nickname or line_user.display_name or user_id[:12],
                        'oa_name': line_account.name,
                        'last_message_prefix': 'ลูกค้า:',
                        'last_message_content': new_msg.message_text if new_msg.message_type == 'text' else f"[{new_msg.message_type.capitalize()}]",
                        'status': 'unread',
                        'picture_url': line_user.picture_url
                    })

        # --- [แก้ไข] บันทึกทุกอย่างลง DB แค่ครั้งเดียวหลังจบ Loop ---
        
        return "OK", 200

    except InvalidSignatureError:
        return "Invalid signature", 400
    except Exception as e:
        db.session.rollback()
        print("Error:", str(e))

        import traceback
        traceback.print_exc()
        return "Internal Server Error", 500
    
@socketio.on("join")
def on_join(data):
    """เมื่อ Client ต้องการเข้าร่วมห้องแชท"""
    room = data['room']
    join_room(room)
    print(f"✅ Admin has entered the room: {room}")

@socketio.on("leave")
def on_leave(data):
    """เมื่อ Client ต้องการออกจากห้องแชท"""
    room = data['room']
    leave_room(room)
    print(f"🚪 Admin has left the room: {room}")

@socketio.on("connect")
def on_connect():
    print("⚡ client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("⚡ client disconnected")