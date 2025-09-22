import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app, url_for , Response 
from flask import Blueprint, render_template, request , session , abort 
from flask_login import login_required , current_user
from app.extensions import db
from datetime import datetime, timedelta
from . import bp   # ใช้ bp ที่ import มาจาก __init__.py
from flask import jsonify
from app.models import  db 
from sqlalchemy import func
from linebot import LineBotApi
from linebot.models import TextSendMessage , ImageSendMessage , StickerSendMessage
from linebot.exceptions import LineBotApiError
from sqlalchemy import or_
from app.models import User, LineUser, LineAccount, LineMessage, QuickReply, OAGroup, Sticker
import traceback
from app.extensions import socketio


@bp.route("/")
@login_required
def index():
    all_groups = OAGroup.query.order_by(OAGroup.name).all()
    selected_group_ids = session.get("active_group_ids", [])
    status_filter = request.args.get('status_filter', 'all')

    # [แก้ไข] แก้ไข Subquery ให้ Group by ทั้ง user_id และ line_account_id
    subquery = db.session.query(
        LineMessage.user_id,
        LineMessage.line_account_id,
        func.max(LineMessage.timestamp).label('max_timestamp')
    ).group_by(LineMessage.user_id, LineMessage.line_account_id).subquery()

    # [แก้ไข] แก้ไขการ Join ให้ตรงกับ Subquery ใหม่
    query = db.session.query(
        LineMessage, LineUser
    ).join(
        subquery,
        (LineMessage.user_id == subquery.c.user_id) &
        (LineMessage.line_account_id == subquery.c.line_account_id) & # <-- เพิ่มเงื่อนไข Join
        (LineMessage.timestamp == subquery.c.max_timestamp)
    ).join(
        LineUser,
        (LineMessage.user_id == LineUser.user_id) &
        (LineMessage.line_account_id == LineUser.line_account_id)
    )

    if status_filter != 'all':
        query = query.filter(LineUser.status == status_filter)

    if selected_group_ids:
        query = query.join(LineAccount, LineMessage.line_account_id == LineAccount.id)\
                     .filter(LineAccount.groups.any(OAGroup.id.in_(selected_group_ids)))

    users_with_messages = query.order_by(subquery.c.max_timestamp.desc()).all()

    conversations = []
    for msg, user in users_with_messages:
        unread_count = 0
        if user.last_read_timestamp:
            # นับข้อความที่มาจากลูกค้า (is_outgoing=False) และใหม่กว่าเวลาที่อ่านล่าสุด
            unread_count = LineMessage.query.filter(
                LineMessage.user_id == user.user_id,
                LineMessage.line_account_id == user.line_account_id,
                LineMessage.is_outgoing == False,
                LineMessage.timestamp > user.last_read_timestamp
            ).count()
        else:
            # ถ้ายังไม่เคยอ่านเลย ให้นับข้อความทั้งหมดจากลูกค้า
             unread_count = LineMessage.query.filter_by(
                user_id=user.user_id,
                line_account_id=user.line_account_id,
                is_outgoing=False
            ).count()

        conversations.append({
            "message": msg,
            "user": user,
            "unread_count": unread_count
        })

    return render_template(
        "chats/index.html",
        conversations=conversations,
        all_groups=all_groups,
        selected_group_ids=selected_group_ids,
        status_filter=status_filter
    )


# แก้ไขฟังก์ชัน show(user_id) ทั้งหมดเป็นโค้ดนี้
@bp.route("/<user_id>", endpoint="show")
@login_required
def show(user_id):
    """แสดงประวัติการสนทนาของ user (รองรับ load more)"""
    oa_id = request.args.get("oa", type=int)
    if not oa_id:
        abort(400, "Bad Request: Missing 'oa' parameter in the URL.")
    account = LineAccount.query.get_or_404(oa_id)

    offset = request.args.get("offset", 0, type=int)
    limit = 10

    query = LineMessage.query.filter_by(user_id=user_id)
    if oa_id:
        query = query.filter_by(line_account_id=oa_id)

    total_messages = query.count()

    messages = (
        query.order_by(LineMessage.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    messages = list(reversed(messages))

    # --- ส่วนที่เพิ่มเข้ามาใหม่ ---
    # เตรียมข้อมูลสำหรับ Bubble Chat
    processed_messages = []
    for m in messages:
        # 1. เช็คว่าเป็นข้อความจากแอดมิน (is_outgoing) หรือลูกค้า
        sender_type = 'admin' if m.is_outgoing else 'customer'
        
        # 2. เตรียม content ตามประเภทของข้อความ
        content = ""
        if m.message_type == "text":
            content = m.message_text
        elif m.message_type == "image":
            content = m.message_url
        elif m.message_type == "sticker":
            # สร้าง URL ของสติกเกอร์ให้สมบูรณ์
            content = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{m.sticker_id}/ANDROID/sticker.png"

        # 3. จัดรูปแบบของเวลาให้แสดงแค่ ชั่วโมง:นาที
        formatted_time = m.timestamp.strftime('%H:%M')

        # 4. นำข้อมูลทั้งหมดมาสร้างเป็น Dictionary ใหม่
        processed_messages.append({
            'id': m.id,
            'sender_type': sender_type,
            'message_type': m.message_type,
            'content': content,
            'created_at': formatted_time
        })
    # --- จบส่วนที่เพิ่มเข้ามาใหม่ ---

    quick_replies = QuickReply.query.order_by(QuickReply.created_at.desc()).all()
    line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first()

    return render_template(
        "chats/show.html",
        account=account,
        user_id=user_id,
        messages=processed_messages,  # <--- ส่งข้อมูลที่ประมวลผลแล้วไปแทน
        oa_id=oa_id,
        offset=offset,
        limit=limit,
        total_messages=total_messages,
        quick_replies=quick_replies,
        line_user=line_user
    )



# ในไฟล์ app/blueprints/chats/routes.py
@bp.route("/api/messages/<user_id>")
@login_required
def get_messages_for_user(user_id):
    oa_id = request.args.get("oa", type=int)
    if not oa_id:
        return jsonify({"error": "Missing OA ID"}), 400
    account = LineAccount.query.get(oa_id)
    line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first()
    if not account or not line_user:
        return jsonify({"error": "User or Account not found"}), 404
    
    status_was_changed = False
    if line_user.status == 'unread':
        line_user.status = 'read'
        status_was_changed = True

    line_user.last_read_timestamp = datetime.utcnow()
    db.session.commit()

    # [แก้ไข] ถ้าสถานะเพิ่งถูกเปลี่ยน ให้ส่งข้อมูลแชททั้งก้อนไปอัปเดต
    if status_was_changed:
        latest_message = LineMessage.query.filter_by(
            user_id=line_user.user_id, line_account_id=line_user.line_account_id
        ).order_by(LineMessage.timestamp.desc()).first()

        line_account = LineAccount.query.get(line_user.line_account_id)
        oa_name = line_account.name if line_account else "Unknown OA"

        last_message_prefix = ""
        last_message_content = "[No messages yet]"
        if latest_message:
            last_message_prefix = "คุณ:" if latest_message.is_outgoing else "ลูกค้า:"
            if latest_message.message_type == 'text':
                last_message_content = latest_message.message_text
            elif latest_message.message_type == 'event':
                last_message_content = latest_message.message_text
            else:
                last_message_content = f"[{latest_message.message_type.capitalize()}]"

        conversation_data = {
            'user_id': line_user.user_id,
            'line_account_id': line_user.line_account_id,
            'display_name': line_user.nickname or line_user.display_name or f"User: {line_user.user_id[:12]}...",
            'oa_name': oa_name,
            'last_message_prefix': last_message_prefix,
            'last_message_content': last_message_content,
            'status': line_user.status,
            'picture_url': line_user.picture_url
        }
        socketio.emit('update_conversation_list', conversation_data)

    
    total_messages = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id).count()
    messages_query = LineMessage.query.filter_by(
        user_id=user_id,
        line_account_id=oa_id
    ).order_by(LineMessage.timestamp.desc()).limit(10).all() # [แนะนำ] เรียงจากเก่าไปใหม่เลย
    messages_query.reverse()
    processed_messages = []
    for m in messages_query:
        sender_type = 'admin' if m.is_outgoing else 'customer'
        content = ""
        is_close_event = False

        if m.message_type == "text":
            content = m.message_text
        elif m.message_type == "image":
            content = m.message_url
        elif m.message_type == "sticker":
            content = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{m.sticker_id}/ANDROID/sticker.png"
        elif m.message_type == "event":
            content = m.message_text
            if "'Closed'" in content:
                is_close_event = True

        if m.is_outgoing:
            local_timestamp = m.timestamp + timedelta(hours=7)
        else:
            local_timestamp = m.timestamp
            
        message_data = {
            'id': m.id,
            'sender_type': sender_type,
            'message_type': m.message_type,
            'content': content,
            'created_at': local_timestamp.strftime('%H:%M'),
            'full_datetime': local_timestamp.strftime('%d %b - %H:%M'),
            'is_close_event': is_close_event # <-- [เพิ่ม] บรรทัดที่ขาดไปอยู่ตรงนี้ครับ
        }

        if m.is_outgoing and m.admin:
            message_data['admin_email'] = m.admin.email
            message_data['oa_name'] = m.line_account.name
        processed_messages.append(message_data)

    response_data = {
        "user": {
            "db_id": line_user.id,
            "user_id": line_user.user_id,
            "display_name": line_user.display_name,
            "nickname": line_user.nickname or '',
            "phone": line_user.phone or '',
            "note": line_user.note or '',
            "status": line_user.status
        },
        "account": {
            "id": account.id,
            "name": account.name
        },
        "messages": processed_messages,
        "total_messages": total_messages
    }

    return jsonify(response_data)

@bp.route("/api/send_message", methods=["POST"])
@login_required
def send_message():
    data = request.get_json()
    user_id = data.get('user_id')
    oa_id = data.get('oa_id')
    message_text = data.get('message')

    if not all([user_id, oa_id, message_text]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    account = LineAccount.query.get(oa_id)
    if not account:
        return jsonify({"status": "error", "message": "OA not found"}), 404

    # --- ส่วนที่ปรับปรุง ---
    line_api_error_message = None # สร้างตัวแปรไว้เก็บ error จาก LINE
    try:
        line_bot_api = LineBotApi(account.channel_access_token)
        message_to_send = TextSendMessage(text=message_text)
        line_bot_api.push_message(user_id, message_to_send)
    
    except LineBotApiError as e:
        line_api_error_message = e.error.message
        print(f"LINE API Error: {line_api_error_message}")
    except Exception as e:
        line_api_error_message = str(e)
        print(f"An unexpected error occurred while sending to LINE: {line_api_error_message}")
    # --- จบส่วนที่ปรับปรุง ---

    # บันทึกข้อความที่ส่งลงฐานข้อมูลของเรา (ส่วนนี้ทำงานไม่ว่า LINE จะส่งสำเร็จหรือไม่)
    try:
        new_message = LineMessage(
            user_id=user_id,
            line_account_id=oa_id,
            message_type='text',
            message_text=message_text,
            is_outgoing=True,
            timestamp=datetime.utcnow(),
            admin_user_id=current_user.id
            # ในอนาคตอาจเพิ่ม field `sent_status` เพื่อเก็บ error message ได้
            # sent_status = line_api_error_message 
        )
        db.session.add(new_message)
        db.session.commit()

        room_name = f"chat_{user_id}_{oa_id}"
        message_data_for_socket = {
            'id': new_message.id,
            'sender_type': 'admin',
            'message_type': new_message.message_type,
            'content': new_message.message_text,
            'full_datetime': (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
            'admin_email': current_user.email,
            'oa_name': new_message.line_account.name,
            'user_id': user_id,
            'oa_id': int(oa_id)
        }
        socketio.emit('new_message', message_data_for_socket, to=room_name)

        line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first()
        if line_user:
            conversation_data = {
                'user_id': user_id,
                'line_account_id': int(oa_id),
                'display_name': line_user.nickname or line_user.display_name or f"User: {user_id[:12]}...",
                'oa_name': new_message.line_account.name,
                'last_message_prefix': "คุณ:", # เพราะเป็นข้อความจากแอดมิน
                'last_message_content': new_message.message_text,
                'status': line_user.status,
                'picture_url': line_user.picture_url
            }
            socketio.emit('update_conversation_list', conversation_data)

        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving message to DB: {e}")
        return jsonify({"status": "error", "message": "Failed to save message to database"}), 500

    # ส่งสถานะกลับไปให้ JavaScript พร้อมบอกว่าส่งไป LINE สำเร็จหรือไม่
    return jsonify({
        "status": "success",
        "db_saved_successfully": True, # <--- JavaScript ต้องการตัวนี้
        "id": new_message.id,
        "message_type": new_message.message_type,
        "content": new_message.message_text,
        "full_datetime": (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        "admin_email": current_user.email,
        "oa_name": new_message.line_account.name,
        "sender_type": 'admin' # <--- เพิ่ม sender_type ด้วย
    })

# แก้ไขข้อมูล users
@bp.route('/user/update/<int:id>', methods=['POST'])
@login_required
def update_details(id):
    # โค้ดส่วนนี้จะเหมือนกับ UserMixin ไม่ต้องใช้ LineUser
    from app.models import User
    user = User.query.get_or_404(id)

    # ดึงข้อมูลจากฟอร์ม
    user.real_name = request.form.get('real_name')
    user.phone_number = request.form.get('phone_number')
    user.note = request.form.get('note')

    # บันทึกลงฐานข้อมูล
    db.session.commit()

    flash('User details updated successfully!', 'success')

    # กลับไปที่หน้าที่มา (หน้าแชท)
    next_url = request.args.get('next')
    return redirect(next_url or url_for('chats.index'))


# API ค้นหาอย่างเร็ว (LIKE)
@bp.route("/search")
@login_required
def search_messages():
    q = request.args.get("q", "").strip()
    oa_id = request.args.get("oa", type=int)

    if not q:
        flash("กรุณากรอกคำค้นหา", "warning")
        return redirect(url_for("chats.index"))

    query = LineMessage.query
    if oa_id:
        query = query.filter_by(line_account_id=oa_id)

    results = (
        query.filter(LineMessage.message_text.ilike(f"%{q}%"))
        .order_by(LineMessage.timestamp.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "chats/search_results.html",
        query=q,
        results=results,
        oa_id=oa_id
    )

# send_image
@bp.route('/api/send_image', methods=['POST'])
@login_required
def send_image():
    """
    จัดการการอัปโหลดและส่งข้อความรูปภาพไปยัง LINE
    พร้อมทั้งบันทึกประวัติลงฐานข้อมูลอย่างปลอดภัย
    """
    file_path = None
    # สร้างโครงสร้างข้อมูลสำหรับตอบกลับไว้ล่วงหน้า
    response_data = {
        "line_sent_successfully": False,
        "line_error": "An unknown error occurred.",
        "db_saved_successfully": False,
        "db_error": "An unknown error occurred."
    }

    try:
        # 1. ตรวจสอบและรับข้อมูลจาก Request
        if 'image' not in request.files:
            return jsonify({"error": "No image part"}), 400
        
        file = request.files['image']
        user_id = request.form.get('user_id')
        oa_id = request.form.get('oa_id')

        if not all([file, user_id, oa_id]) or file.filename == '':
            return jsonify({"error": "Missing data or file"}), 400

        # 2. สร้างชื่อไฟล์ใหม่และบันทึกไฟล์ลง Server
        _, f_ext = os.path.splitext(file.filename)
        filename = str(uuid.uuid4()) + f_ext
        
        project_root = os.path.dirname(current_app.root_path) 
        upload_folder = os.path.join(project_root, 'static', 'uploads')
        
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        # 3. สร้าง URL แบบ HTTPS สำหรับส่งให้ LINE
        image_url = url_for('static', filename=f'uploads/{filename}', _external=True, _scheme='https')
        print(f"Generated URL to send to LINE: {image_url}")
        
        # 4. ส่งข้อความรูปภาพไปที่ LINE API
        try:
            account = LineAccount.query.get(oa_id)
            if account:
                line_bot_api = LineBotApi(account.channel_access_token)
                message_to_send = ImageSendMessage(
                    original_content_url=image_url, 
                    preview_image_url=image_url
                )
                line_bot_api.push_message(user_id, message_to_send)
                # อัปเดตสถานะการส่ง LINE สำเร็จ
                response_data["line_sent_successfully"] = True
                response_data["line_error"] = None
            else:
                response_data["line_error"] = f"OA Account with ID {oa_id} not found."
        except LineBotApiError as e:
            response_data["line_error"] = e.error.message
            print(f"LINE API Error sending image: {response_data['line_error']}")
        except Exception as e:
            response_data["line_error"] = str(e)
            print(f"An unexpected error occurred sending image to LINE: {response_data['line_error']}")
        
        # ถ้าส่ง LINE ไม่สำเร็จ ให้หยุดทำงานและส่ง Error กลับไป
        if not response_data["line_sent_successfully"]:
            # พยายามลบไฟล์ที่อัปโหลดแล้วแต่ส่งไม่สำเร็จทิ้ง
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify(response_data), 500

        # 5. บันทึกประวัติข้อความลงฐานข้อมูล (Database)
        try:
            new_message = LineMessage(
                user_id=user_id,
                line_account_id=oa_id,
                message_type='image',
                message_url=image_url,
                is_outgoing=True,
                timestamp=datetime.utcnow(),
                admin_user_id=current_user.id
            )
            db.session.add(new_message)
            db.session.commit()

            response_data["db_saved_successfully"] = True
            response_data["id"] = new_message.id 
            response_data["sender_type"] = 'admin'
            response_data["message_type"] = 'image'
            response_data["content"] = new_message.message_url
            response_data["full_datetime"] = (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M')
            response_data["admin_email"] = current_user.email
            response_data["oa_name"] = new_message.line_account.name

            room_name = f"chat_{user_id}_{oa_id}"
            message_data_for_socket = {
                'id': new_message.id,
                'sender_type': 'admin',
                'message_type': 'image',
                'content': new_message.message_url,
                'full_datetime': (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
                'admin_email': current_user.email,
                'oa_name': new_message.line_account.name,
                'user_id': user_id,
                'oa_id': int(oa_id)
            }
            socketio.emit('new_message', message_data_for_socket, to=room_name)

        except Exception as e:
            db.session.rollback() # สำคัญมาก: ย้อนสถานะ DB กลับไปก่อนหน้า
            print("❌ FAILED to save message to DB. Rolling back.")
            print("-------------------- DATABASE ERROR --------------------")
            traceback.print_exc() # พิมพ์ Error ของ DB แบบละเอียด
            print("------------------------------------------------------")
            response_data["db_saved_successfully"] = False
            response_data["db_error"] = str(e)
        
        return jsonify(response_data)

    except Exception as e:
        # บล็อกนี้จะทำงานหากเกิด Error ร้ายแรงอื่นๆ นอกเหนือจากที่ดักไว้
        db.session.rollback()
        print(f"An overarching error occurred in send_image function: {e}")
        traceback.print_exc()
        # พยายามลบไฟล์ทิ้งหากมี
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"error": "An internal server error occurred"}), 500
    
# Sticker
@bp.route("/api/send_sticker", methods=["POST"])
@login_required
def send_sticker():
    data = request.get_json()
    user_id = data.get('user_id')
    package_id = data.get('package_id')
    sticker_id = data.get('sticker_id')
    oa_id_str = data.get('oa_id')
    oa_id = int(oa_id_str) if oa_id_str else None

    if not all([user_id, oa_id, package_id, sticker_id]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    account = LineAccount.query.get(oa_id)
    if not account:
        return jsonify({"status": "error", "message": "OA not found"}), 404

    # --- ส่ง Sticker ผ่าน LINE API ---
    try:
        line_bot_api = LineBotApi(account.channel_access_token)
        message_to_send = StickerSendMessage(package_id=package_id, sticker_id=sticker_id)
        line_bot_api.push_message(user_id, message_to_send)
    except Exception as e:
        print(f"Error sending LINE sticker message: {e}")
        return jsonify({"status": "error", "message": "Failed to send sticker via LINE"}), 500

    # --- บันทึกลงฐานข้อมูล ---
    new_message = LineMessage(
        user_id=user_id,
        line_account_id=oa_id,
        message_type='sticker',
        package_id=package_id,
        sticker_id=sticker_id,
        is_outgoing=True,
        timestamp=datetime.utcnow(),
        admin_user_id=current_user.id
    )
    db.session.add(new_message)
    db.session.commit()

    room_name = f"chat_{user_id}_{oa_id}"
    sticker_url = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{new_message.sticker_id}/ANDROID/sticker.png"
    message_data_for_socket = {
        'id': new_message.id,
        'sender_type': 'admin',
        'message_type': 'sticker',
        'content': sticker_url,
        'full_datetime': (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        'admin_email': current_user.email,
        'oa_name': new_message.line_account.name,
        'user_id': user_id,
        'oa_id': int(oa_id)
    }
    socketio.emit('new_message', message_data_for_socket, to=room_name)

    return jsonify({
        "status": "success",
        "db_saved_successfully": True, # <--- JavaScript ต้องการตัวนี้
        "id": new_message.id,
        "sender_type": 'admin',
        "message_type": "sticker",
        "content": sticker_url,
        "full_datetime": (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        "admin_email": current_user.email,
        "oa_name": new_message.line_account.name
    })


@bp.route('/api/quick_replies/<int:oa_id>')
@login_required
def get_quick_replies(oa_id):
    """
    API สำหรับดึง Quick Replies ที่เกี่ยวข้องกับ OA นั้นๆ
    จะดึงทั้งแบบ Global และแบบ Specific OA
    """
    replies = QuickReply.query.filter(
        or_(QuickReply.line_account_id == None, QuickReply.line_account_id == oa_id)
    ).order_by(QuickReply.shortcut).all()

    reply_list = [
        {"shortcut": r.shortcut, "message": r.message} for r in replies
    ]
    return jsonify(reply_list)

@bp.route('/api/user_info/<int:user_db_id>', methods=['POST'])
@login_required
def update_user_info(user_db_id):
    user = LineUser.query.get_or_404(user_db_id)
    data = request.get_json()
    
    new_nickname = data.get('nickname', '')
    new_phone = data.get('phone', '')
    new_note = data.get('note', '')

    log_messages = []

    # [แก้ไข] เปลี่ยน current_user.username เป็น current_user.email
    if user.nickname != new_nickname:
        log_messages.append(f"📝 {current_user.email} changed Nickname to '{new_nickname}'")
        user.nickname = new_nickname
        
    if user.phone != new_phone:
        log_messages.append(f"📝 {current_user.email} changed Phone to '{new_phone}'")
        user.phone = new_phone
        
    if user.note != new_note:
        log_messages.append(f"📝 {current_user.email} changed Note")
        user.note = new_note

    # สร้างข้อความ Log ในแชท ถ้ามีการเปลี่ยนแปลง
    if log_messages:
        for log_text in log_messages:
            log_message = LineMessage(
                user_id=user.user_id,
                line_account_id=user.line_account_id,
                message_type='event',
                message_text=log_text,
                is_outgoing=True,
                timestamp=datetime.utcnow()
            )
            db.session.add(log_message)
            
    db.session.commit()
    return jsonify({"status": "success", "message": "User info updated."})

# API Endpoint สำหรับดึงรายการสติกเกอร์ทั้งหมด
@bp.route('/api/stickers')
@login_required
def api_stickers():
    try:
        # ดึงสติกเกอร์ทั้งหมดจากฐานข้อมูล
        stickers = Sticker.query.all()
        
        # แปลงข้อมูล SQLAlchemy object ให้เป็น list ของ dictionary ที่ JavaScript ใช้งานได้
        sticker_list = [
            {'packageId': s.packageId, 'stickerId': s.stickerId} 
            for s in stickers
        ]
        
        # ส่งข้อมูลกลับไปในรูปแบบ JSON
        return jsonify(sticker_list)
        
    except Exception as e:
        # กรณีเกิดข้อผิดพลาด
        print(f"Error fetching stickers: {e}")
        return jsonify({"error": "Could not fetch stickers"}), 500
    

# โหลดข้อความ
@bp.route("/download/<user_id>")
@login_required
def download_chat(user_id):
    oa_id = request.args.get("oa", type=int)
    if not oa_id:
        return "Missing OA ID", 400

    line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first_or_404()
    messages = LineMessage.query.filter_by(
        user_id=user_id,
        line_account_id=oa_id
    ).order_by(LineMessage.timestamp.asc()).all()

    # สร้างเนื้อหาไฟล์ Text
    chat_history_text = f"Chat History for {line_user.display_name} ({user_id})\n"
    chat_history_text += "=" * 40 + "\n\n"

    for msg in messages:
        local_time = msg.timestamp + timedelta(hours=7)
        timestamp_str = local_time.strftime('%Y-%m-%d %H:%M:%S')
        
        sender = f"Admin ({msg.admin.email})" if msg.is_outgoing and msg.admin else f"Customer ({line_user.display_name})"
        
        content = ""
        if msg.message_type == 'text':
            content = msg.message_text
        elif msg.message_type == 'image':
            content = f"[Image]: {msg.message_url}"
        elif msg.message_type == 'sticker':
            content = f"[Sticker]: ID {msg.sticker_id}"
        elif msg.message_type == 'event':
            content = f"--- {msg.message_text} ---"
        
        chat_history_text += f"[{timestamp_str}] {sender}:\n{content}\n\n"

    # สร้าง Response เพื่อให้ Browser ดาวน์โหลดเป็นไฟล์ .txt
    return Response(
        chat_history_text,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=chat_{user_id}.txt"}
    )    


# ดูประวัติแชทเพิ่มเติม    
@bp.route("/<user_id>/more")
@login_required
def load_more(user_id):
    """API สำหรับโหลดข้อความเก่าเพิ่มเติม"""
    oa_id = request.args.get("oa", type=int)
    offset = request.args.get("offset", type=int, default=0)
    limit = 10 # โหลดเพิ่มทีละ 10

    messages = LineMessage.query.filter_by(
        user_id=user_id,
        line_account_id=oa_id
    ).order_by(LineMessage.timestamp.desc()).offset(offset).limit(limit).all()
    messages.reverse()

    processed_messages = []
    # ... (ส่วน for loop เหมือนเดิมทุกประการ) ...
    for m in messages:
        sender_type = 'admin' if m.is_outgoing else 'customer'
        content = ""
        if m.message_type == "text": content = m.message_text
        elif m.message_type == "image": content = m.message_url
        elif m.message_type == "sticker": content = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{m.sticker_id}/ANDROID/sticker.png"
        elif m.message_type == "event": content = m.message_text
        local_timestamp = m.timestamp + timedelta(hours=7) if m.is_outgoing else m.timestamp
        message_data = {
            'sender_type': sender_type, 'message_type': m.message_type, 'content': content,
            'created_at': local_timestamp.strftime('%H:%M'), 'full_datetime': local_timestamp.strftime('%d %b - %H:%M')
        }
        if m.is_outgoing and m.admin:
            message_data['admin_email'] = m.admin.email
            message_data['oa_name'] = m.line_account.name
        processed_messages.append(message_data)
        
    return jsonify({"messages": processed_messages})


# ช่องค้นหา sidebar chats windows
@bp.route('/api/search_conversations')
@login_required
def search_conversations():
    """API สำหรับค้นหา user/conversation"""
    query_term = request.args.get('q', '').strip()
    selected_group_ids = session.get("active_group_ids", [])

    if not query_term:
        # ถ้าไม่มีคำค้นหา ก็ส่งค่าว่างกลับไป
        return jsonify([])

    # ค้นหาใน LineUser จาก nickname, phone, user_id
    user_query = LineUser.query.filter(
        or_(
            LineUser.nickname.ilike(f"%{query_term}%"),
            LineUser.phone.ilike(f"%{query_term}%"),
            LineUser.user_id.ilike(f"%{query_term}%")
        )
    )

    # กรองตาม OA Group ที่เลือกไว้ (ถ้ามี)
    if selected_group_ids:
        user_query = user_query.join(LineAccount).filter(LineAccount.groups.any(OAGroup.id.in_(selected_group_ids)))

    found_users = user_query.limit(20).all() # จำกัดผลการค้นหาที่ 20 คน

    # เตรียมข้อมูลเพื่อส่งกลับในรูปแบบเดียวกับตอนโหลดหน้าครั้งแรก
    results = []
    for user in found_users:
        # หาข้อความล่าสุดของ user คนนี้
        latest_message = LineMessage.query.filter_by(
            user_id=user.user_id,
            line_account_id=user.line_account_id
        ).order_by(LineMessage.timestamp.desc()).first()

        if latest_message:
            # --- [แก้ไข] เพิ่มข้อมูลสำหรับ UI ใหม่ ---
            
            # กำหนด Prefix สำหรับข้อความล่าสุด
            if latest_message.is_outgoing:
                last_message_prefix = "คุณ:"
            else:
                last_message_prefix = "ลูกค้า:"
            
            # กำหนดเนื้อหาข้อความล่าสุด
            if latest_message.message_type == 'text':
                last_message_content = latest_message.message_text
            else:
                last_message_content = f"[{latest_message.message_type.capitalize()}]"

            results.append({
                'user_id': latest_message.user_id,
                'line_account_id': latest_message.line_account_id,
                'display_name': user.nickname or user.display_name or f"User: {user.user_id[:12]}...",
                'oa_name': latest_message.line_account.name,
                'last_message_prefix': last_message_prefix,
                'last_message_content': last_message_content,
                'is_read': latest_message.is_outgoing, # ใช้ is_outgoing เป็นเงื่อนไขแสดงป้าย Unread ชั่วคราว
                'picture_url': user.picture_url, # ส่ง URL รูปโปรไฟล์ไปด้วย
                'status': user.status
            })

    return jsonify(results)

# ในไฟล์ สถานะของแชท
@bp.route('/api/conversation_status/<int:user_db_id>', methods=['POST'])
@login_required
def update_conversation_status(user_db_id):
    """API สำหรับอัปเดตสถานะของแชท"""
    user = LineUser.query.get_or_404(user_db_id)
    data = request.get_json()
    new_status = data.get('status')

    valid_statuses = ['read', 'deposit', 'withdraw', 'issue', 'closed']
    if not new_status or new_status not in valid_statuses:
        return jsonify({"status": "error", "message": "Invalid status"}), 400

    user.status = new_status
    db.session.commit()

    # สร้าง Log event ในแชท
    log_text = f"📝 {current_user.email} changed status to '{new_status.capitalize()}'"
    log_message = LineMessage(
        user_id=user.user_id,
        line_account_id=user.line_account_id,
        message_type='event',
        message_text=log_text,
        is_outgoing=True, # ให้ถือว่าเป็นข้อความจากแอดมิน
        timestamp=datetime.utcnow()
    )
    db.session.add(log_message)
    db.session.commit()

    latest_message = LineMessage.query.filter_by(
        user_id=user.user_id,
        line_account_id=user.line_account_id
    ).order_by(LineMessage.timestamp.desc()).first()

    line_account = LineAccount.query.get(user.line_account_id)
    oa_name = line_account.name if line_account else "Unknown OA"

    last_message_prefix = ""
    last_message_content = "[No messages yet]"
    if latest_message:
        last_message_prefix = "คุณ:" if latest_message.is_outgoing else "ลูกค้า:"
        if latest_message.message_type == 'text':
            last_message_content = latest_message.message_text
        elif latest_message.message_type == 'event':
             last_message_content = latest_message.message_text
        else:
            last_message_content = f"[{latest_message.message_type.capitalize()}]"
    
    conversation_data = {
        'id': log_message.id,
        'user_id': user.user_id,
        'line_account_id': user.line_account_id,
        'display_name': user.nickname or user.display_name or f"User: {user.user_id[:12]}...",
        'oa_name': oa_name, # <--- [แก้ไข] ใช้ตัวแปร oa_name ที่เราเพิ่งหามา
        'last_message_prefix': last_message_prefix,
        'last_message_content': last_message_content,
        'status': user.status,
        'picture_url': user.picture_url,
        'admin_email': current_user.email,
        'oa_name': user.line_account.name if user.line_account else 'System'
    }
    socketio.emit('update_conversation_list', conversation_data)

    room_name = f"chat_{user.user_id}_{user.line_account_id}"
    message_data_for_socket = {
        'sender_type': 'admin',      # ถือเป็น event จากฝั่งแอดมิน
        'message_type': 'event',     # ประเภทข้อความคือ 'event'
        'content': log_message.message_text, # เอาข้อความจาก Log ที่เพิ่งสร้าง
        'full_datetime': (log_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        'is_close_event': "'Closed'" in log_message.message_text, # เช็คว่าเป็น event ปิดเคสหรือไม่
        'user_id': user.user_id,     # ส่งไปด้วยเพื่อให้ JS เช็คได้ (เผื่อต้องใช้)
        'oa_id': user.line_account_id
    }
    socketio.emit('new_message', message_data_for_socket, to=room_name)

    return jsonify({"status": "success", "new_status": new_status})

# Debug
@bp.route("/debug-paths")
def debug_paths():
    from flask import current_app
    root_path = current_app.root_path
    static_path = current_app.static_folder
    return f"""
        <h1>Flask Debug Info</h1>
        <p><strong>Application Root Path:</strong> {root_path}</p>
        <p><strong>Static Folder Path:</strong> {static_path}</p>
    """