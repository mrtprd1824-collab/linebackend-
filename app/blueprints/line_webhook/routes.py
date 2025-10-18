from flask import abort, request, current_app, jsonify # เพิ่ม abort
from flask_login import login_required, current_user

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
from app.blueprints.chats.routes import _generate_conversation_data, format_message_for_api
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
        abort(404, description="LineAccount not found")

    handler = WebhookHandler(line_account.channel_secret)
    line_bot_api = LineBotApi(line_account.channel_access_token)

    try:
        events = handler.parser.parse(body, signature)

        for event in events:
            # --- จัดการ Event การบล็อก (Unfollow) ---
            if isinstance(event, UnfollowEvent):
                user = LineUser.query.filter_by(user_id=event.source.user_id, line_account_id=line_account.id).first()
                if user:
                    user.is_blocked = True
                continue

            # --- จัดการ Event การแอดเพื่อน/ปลดบล็อก (Follow) ---
            if isinstance(event, FollowEvent):
                user = LineUser.query.filter_by(user_id=event.source.user_id, line_account_id=line_account.id).first()
                if not user:
                    user = LineUser(line_account_id=line_account.id, user_id=event.source.user_id)
                    db.session.add(user)
                
                user.is_blocked = False
                try:
                    profile = line_bot_api.get_profile(event.source.user_id)
                    user.display_name = profile.display_name
                    user.picture_url = profile.picture_url
                except Exception as e:
                    print(f"Could not get profile for follower {event.source.user_id}: {e}")
                continue

            # --- จัดการ Event ที่เป็นข้อความ (MessageEvent) ---
            if isinstance(event, MessageEvent):
                user = LineUser.query.filter_by(line_account_id=line_account.id, user_id=event.source.user_id).first()

                if not user:
                    user = LineUser(line_account_id=line_account.id, user_id=event.source.user_id)
                    db.session.add(user)
                    try:
                        profile = line_bot_api.get_profile(event.source.user_id)
                        user.display_name = profile.display_name
                        user.picture_url = profile.picture_url
                    except Exception as e:
                        print(f"Could not get profile for {event.source.user_id}: {e}")
                
                # [ปรับปรุง] อัปเดตสถานะและเวลา
                previous_status = (user.status or "").strip().lower()
                should_reset_status = previous_status in ("", "read", "unread") or previous_status == "closed"
                if should_reset_status:
                    user.status = 'unread'
                else:
                    # คงสถานะปัจจุบัน (เช่น deposit/withdraw/issue) เมื่อมีข้อความเข้าใหม่
                    pass
                if should_reset_status:
                    user.read_by_admin_id = None
                user.last_message_at = datetime.utcnow()
                user.is_blocked = False
                # [เอาออก] ไม่มีการจัดการ unread_count ด้วยตนเองอีกต่อไป

                new_msg = None
                if isinstance(event.message, TextMessage):
                    new_msg = LineMessage(line_account_id=line_account.id, user_id=user.user_id, message_type="text", message_text=event.message.text, timestamp=datetime.utcnow(), is_outgoing=False)
                elif isinstance(event.message, ImageMessage):
                    message_content = line_bot_api.get_message_content(event.message.id)
                    image_bytes = message_content.content
                    image_stream = BytesIO(image_bytes)
                    
                    # สร้างไฟล์จำลองเพื่ออัปโหลด (อาจจะต้องสร้าง helper class)
                    class MockFileStorage:
                        def __init__(self, stream, filename, content_type):
                            self.stream, self.filename, self.content_type = stream, filename, content_type
                    
                    mock_file = MockFileStorage(image_stream, f"{event.message.id}.jpg", message_content.content_type)
                    s3_url = s3_client.upload_fileobj(mock_file)
                    if s3_url:
                        new_msg = LineMessage(line_account_id=line_account.id, user_id=user.user_id, message_type="image", message_url=s3_url, timestamp=datetime.utcnow(), is_outgoing=False)
                
                elif isinstance(event.message, StickerMessage):
                    new_msg = LineMessage(line_account_id=line_account.id, user_id=user.user_id, message_type="sticker", sticker_id=event.message.sticker_id, package_id=event.message.package_id, timestamp=datetime.utcnow(), is_outgoing=False)
                
                if new_msg:
                    db.session.add(new_msg)

        # --- [ปรับปรุง] commit ข้อมูลทั้งหมดลง DB แค่ครั้งเดียวหลังจบ Loop ---
        db.session.commit()

        # --- [แก้ไข] ย้ายการ Emit ทั้งหมดมาอยู่นอก Loop และใช้ข้อมูลล่าสุด ---
        # เราจะวน Loop อีกครั้ง แต่ครั้งนี้เพื่อ Emit เท่านั้น
        for event in events:
            if isinstance(event, MessageEvent):
                user = LineUser.query.filter_by(line_account_id=line_account.id, user_id=event.source.user_id).first()
                
                # ค้นหาข้อความล่าสุดที่เพิ่งบันทึกไป
                last_message = LineMessage.query.filter_by(user_id=user.user_id, line_account_id=line_account.id).order_by(LineMessage.timestamp.desc()).first()

                if user and last_message:
                    message_data_for_socket = format_message_for_api(last_message)
                    fresh_data = _generate_conversation_data(user.user_id, user.line_account_id)

                    # ★★★ แก้ไขโดยการส่ง Event ทั้งสองตัวไปที่ "ห้องของกลุ่ม" ★★★
                    if fresh_data and user.line_account and user.line_account.groups:
                        for group in user.line_account.groups:
                            group_room_name = f'group_{group.id}'
                            # 1. ส่ง new_message ไปที่กลุ่ม (สำหรับเสียง/Pop-up/แชทที่เปิดอยู่)
                            socketio.emit('new_message', message_data_for_socket, to=group_room_name)
                            # 2. ส่ง render_conversation_update ไปที่กลุ่ม (สำหรับ Sidebar)
                            socketio.emit('render_conversation_update', fresh_data, to=group_room_name)
        
        return "OK", 200

    except InvalidSignatureError:
        abort(400, description="Invalid signature")
    except Exception as e:
        db.session.rollback()
        print(f"Error in webhook callback: {e}")
        import traceback
        traceback.print_exc()
        abort(500, description="Internal Server Error")
    
@bp.route("/chats/read", methods=["POST"])
@login_required
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
        now = datetime.utcnow()
        previous_status = (user.status or "").strip().lower()
        if user.unread_count > 0:
            user.unread_count = 0
        if previous_status in ("", "unread", "read"):
            user.status = "read"
        user.last_read_timestamp = now
        user.read_by_admin_id = current_user.id
        db.session.commit()

        fresh_data = _generate_conversation_data(user.user_id, user.line_account_id)
        if fresh_data and user.line_account and user.line_account.groups:
            for group in user.line_account.groups:
                group_room_name = f'group_{group.id}'
                socketio.emit('render_conversation_update', fresh_data, to=group_room_name)

        print(f"✅ Marked chat for user {user_id} as read (triggered by {current_user.email}).")
        return jsonify({'success': True, 'data': fresh_data}), 200

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
