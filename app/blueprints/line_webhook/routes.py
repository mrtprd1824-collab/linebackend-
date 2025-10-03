from flask import abort, request, current_app, jsonify # เพิ่ม abort

# [เพิ่ม] import เครื่องมือ S3 ของคุณ
from app.services import s3_client

from flask_socketio import join_room, leave_room
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from app.models import db, LineAccount, LineMessage, LineUser
from . import bp
import json
import os
from datetime import datetime

from app.extensions import socketio
from linebot.models import (
    FollowEvent, UnfollowEvent, MessageEvent,
    TextMessage, ImageMessage, StickerMessage
)
from io import BytesIO


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
        events = handler.parser.parse(body, signature)

        for event in events:
            # --- 1. จัดการ Event การบล็อก (Unfollow) ---
            if isinstance(event, UnfollowEvent):
                user_id = event.source.user_id
                user = LineUser.query.filter_by(user_id=user_id, line_account_id=line_account.id).first()
                if user:
                    user.is_blocked = True
                    db.session.commit()
                    print(f">>> User {user_id} has BLOCKED/UNFOLLOWED. Marked as blocked.")
                continue # จบการทำงานสำหรับ Event นี้

            # --- 2. จัดการ Event การแอดเพื่อน/ปลดบล็อก (Follow) ---
            if isinstance(event, FollowEvent):
                user_id = event.source.user_id
                user = LineUser.query.filter_by(user_id=user_id, line_account_id=line_account.id).first()

                if not user: # ถ้าเป็น user ใหม่ที่ไม่เคยมีใน DB มาก่อน
                    user = LineUser(line_account_id=line_account.id, user_id=user_id)
                    db.session.add(user)
                
                user.is_blocked = False # ไม่ว่าจะแอดใหม่หรือปลดบล็อก สถานะคือ "ไม่ถูกบล็อก"
                
                try: # พยายามดึงโปรไฟล์
                    profile = line_bot_api.get_profile(user_id)
                    user.display_name = profile.display_name
                    user.picture_url = profile.picture_url
                except Exception as e:
                    print(f"Could not get profile for new follower {user_id}: {e}")
                
                db.session.commit()
                print(f">>> User {user_id} has FOLLOWED/UNBLOCKED. Marked as NOT blocked.")
                continue # จบการทำงานสำหรับ Event นี้

            # --- 3. จัดการ Event ที่เป็นข้อความ (MessageEvent) ---
            if isinstance(event, MessageEvent):
                user_id = event.source.user_id
                line_user = LineUser.query.filter_by(line_account_id=line_account.id, user_id=user_id).first()

                # สร้าง user ถ้ายังไม่มี (กรณีที่ได้รับข้อความครั้งแรก แต่ไม่มี follow event)
                if not line_user:

                    print(">>> DEBUG: Creating a NEW user entry.")

                    line_user = LineUser(line_account_id=line_account.id, user_id=user_id)
                    line_user.status = 'unread' # <-- กำหนดสถานะเริ่มต้นให้เป็น unread

                    print(f">>> DEBUG: New user status set to: '{line_user.status}'")

                    db.session.add(line_user)
                    try:
                        profile = line_bot_api.get_profile(user_id)
                        line_user.display_name = profile.display_name
                        line_user.picture_url = profile.picture_url
                    except Exception as e:
                        print(f"Could not get profile for {user_id}: {e}")

                else:
                    # --- [DEBUG] เพิ่มบรรทัดนี้เข้าไปในส่วน else ---
                    print(f">>> DEBUG: User already exists. Current status: '{line_user.status}'")


                # อัปเดตสถานะเมื่อได้รับข้อความ
                if line_user.status == 'closed':
                    line_user.status = 'unread'
                line_user.unread_count = (line_user.unread_count or 0) + 1
                line_user.last_seen_at = datetime.utcnow()
                line_user.last_message_at = datetime.utcnow()
                line_user.is_blocked = False # ถ้าส่งข้อความมาได้ แสดงว่าไม่บล็อก
                db.session.commit()

                # บันทึกข้อความลง DB
                msg_type = event.message.type
                new_msg = None

                if isinstance(event.message, TextMessage):
                    new_msg = LineMessage(
                        line_account_id=line_account.id, user_id=user_id,
                        message_type="text", message_text=event.message.text,
                        timestamp=datetime.utcnow(), is_outgoing=False
                    )

                # --- ตรวจสอบว่าเป็นข้อความรูปภาพ ---
                elif isinstance(event.message, ImageMessage):
                    message_id = event.message.id
                    message_content = line_bot_api.get_message_content(message_id)

                    class MockFileStorage:
                        def __init__(self, stream, filename, content_type):
                            self.stream = stream
                            self.filename = filename
                            self.content_type = content_type

                    # ★★★ [แก้ไข] เปลี่ยนจาก .iter_content() เป็น .content แล้วใช้ BytesIO ★★★
                    # 1. ดึงข้อมูลรูปภาพทั้งหมดเป็น bytes
                    image_bytes = message_content.content
                    # 2. สร้างไฟล์จำลองในหน่วยความจำจาก bytes
                    image_stream = BytesIO(image_bytes)

                    mock_file = MockFileStorage(
                        stream=image_stream, # <-- ใช้ stream ตัวใหม่
                        filename=f"{message_id}.jpg",
                        content_type=message_content.content_type
                    )
                    
                    s3_url = s3_client.upload_fileobj(mock_file)

                    if s3_url:
                        new_msg = LineMessage(
                            line_account_id=line_account.id, user_id=user_id,
                            message_type="image",
                            message_url=s3_url,
                            timestamp=datetime.utcnow(), is_outgoing=False
                        )

                elif isinstance(event.message, StickerMessage):
                    # ... โค้ดส่วนนี้เหมือนเดิม ...
                    new_msg = LineMessage(
                        line_account_id=line_account.id, user_id=user_id,
                        message_type="sticker",
                        sticker_id=event.message.sticker_id,
                        package_id=event.message.package_id,
                        timestamp=datetime.utcnow(), is_outgoing=False
                    )
                else:
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
                })

                socketio.emit('resort_sidebar', {
                    'user_id': user_id,
                    'line_account_id': line_account.id,
                    'display_name': line_user.nickname or line_user.display_name or user_id[:12],
                    'oa_name': line_account.name,
                    'last_message_prefix': 'ลูกค้า:',
                    'last_message_content': new_msg.message_text if new_msg.message_type == 'text' else f"[{new_msg.message_type.capitalize()}]",
                    'status': line_user.status,
                    'unread_count': line_user.unread_count,
                    'picture_url': line_user.picture_url
                })

                pass
                

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
    
@bp.route("/chats/read", methods=["POST"])
def mark_chat_as_read():
    """Endpoint สำหรับเคลียร์ unread_count เมื่อแอดมินเปิดอ่านแชท"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

    user_id = data.get('user_id')
    line_account_id = data.get('oa_id') # เปลี่ยนจาก line_account_id เป็น oa_id ให้ตรงกับที่ JS จะส่งมา

    if not user_id or not line_account_id:
        return jsonify({'success': False, 'error': 'Missing user_id or oa_id'}), 400

    # ค้นหา user ในฐานข้อมูล
    user = LineUser.query.filter_by(user_id=str(user_id), line_account_id=int(line_account_id)).first()
    
    if user:
        if user.unread_count > 0:
            user.unread_count = 0
            db.session.commit()
            print(f"✅ Marked chat for user {user_id} as read.")
            return jsonify({'success': True, 'message': 'Unread count cleared.'}), 200
        else:
            # ไม่ต้องทำอะไรถ้ามันเป็น 0 อยู่แล้ว
            return jsonify({'success': True, 'message': 'No unread messages to clear.'}), 200

    return jsonify({'success': False, 'error': 'User not found'}), 404
    
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