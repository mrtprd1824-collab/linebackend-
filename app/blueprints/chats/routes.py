import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app, url_for , Response 
from flask import Blueprint, render_template, request , session , abort 
from flask_login import login_required , current_user
from app.extensions import db
from datetime import datetime, timedelta , timezone
from . import bp   # ใช้ bp ที่ import มาจาก __init__.py
from flask import jsonify
from app.models import  db 
from sqlalchemy import func, case
from linebot import LineBotApi
from linebot.models import TextSendMessage , ImageSendMessage , StickerSendMessage
from linebot.exceptions import LineBotApiError
from sqlalchemy import or_
from app.models import User, LineUser, LineAccount, LineMessage, QuickReply, OAGroup, Sticker
import traceback
from app.extensions import socketio
from app.blueprints.chats import bp
from app.services import s3_client

def truncate_text(text, length=10):
    """ตัดข้อความและต่อท้ายด้วย '...' ถ้ามันยาวเกินที่กำหนด"""
    if text and len(text) > length:
        return text[:length] + '...'
    return text


@bp.route("/")
@login_required
def index():
    all_groups = OAGroup.query.order_by(OAGroup.name).all()
    selected_group_ids = session.get("active_group_ids", [])
    status_filter = request.args.get('status_filter', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20 # <-- กำหนดจำนวนรายการต่อหน้าตรงนี้

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
        
    sort_order = case(
        (LineUser.status == 'closed', 1),
        else_=0
    )
        
    pagination = query.order_by(
        sort_order.asc(),  # 1. เรียงตามเงื่อนไขใหม่ก่อน (0 จะมาก่อน 1)
        subquery.c.max_timestamp.desc() # 2. แล้วค่อยเรียงตามเวลาเหมือนเดิม
    ).paginate(
        page=page, per_page=per_page, error_out=False
    )


    users_with_messages = pagination.items

    conversations = []
    for msg, user in users_with_messages:
        last_unread_timestamp = None

        # 1. สร้าง query พื้นฐานสำหรับนับข้อความที่ยังไม่อ่าน
        query_unread = LineMessage.query.filter(
            LineMessage.user_id == user.user_id,
            LineMessage.line_account_id == user.line_account_id,
            LineMessage.is_outgoing == False
        )

        # 2. เพิ่มเงื่อนไขเวลา ถ้าเคยอ่านแล้ว
        if user.last_read_timestamp:
            query_unread = query_unread.filter(LineMessage.timestamp > user.last_read_timestamp)
        
        # 3. นับจำนวนข้อความที่ยังไม่อ่านจาก query ที่สร้างไว้
        unread_count = query_unread.count()

        # 4. ถ้ามีข้อความที่ยังไม่อ่าน ให้หาเวลาของข้อความล่าสุด
        if unread_count > 0:
            last_unread_message = query_unread.order_by(LineMessage.timestamp.desc()).first()
            if last_unread_message:
                # แปลงเป็น unix timestamp (วินาที)
                last_unread_timestamp = last_unread_message.timestamp.replace(tzinfo=timezone.utc).timestamp()

        conversations.append({
            "message": msg,
            "user": user,
            "unread_count": unread_count,
            "last_unread_timestamp": last_unread_timestamp
        })

    return render_template(
        "chats/index.html",
        conversations=conversations,
        pagination=pagination,
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
                last_message_content = truncate_text(latest_message.message_text)
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
            'picture_url': line_user.picture_url,
            'line_sent_successfully': latest_message.line_sent_successfully if latest_message else True,
            'line_error_message': latest_message.line_error_message if latest_message else None
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

        local_timestamp = m.timestamp + timedelta(hours=7)
            
        message_data = {
            'id': m.id,
            'sender_type': sender_type,
            'message_type': m.message_type,
            'content': content,
            'created_at': local_timestamp.strftime('%H:%M'),
            'full_datetime': local_timestamp.strftime('%d %b - %H:%M'),
            'is_close_event': is_close_event,
            'line_sent_successfully': m.line_sent_successfully,
            'line_error_message': m.line_error_message
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
            "name": account.name,
            "manager_url": account.manager_url
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
    line_sent_successfully = True
    line_api_error_message = None # สร้างตัวแปรไว้เก็บ error จาก LINE

    try:
        line_bot_api = LineBotApi(account.channel_access_token)

        message_to_send = TextSendMessage(text=message_text)
        line_bot_api.push_message(user_id, message_to_send)

        today_str = (datetime.utcnow()).strftime('%Y%m%d') # ใช้วันที่ของ UTC
        delivery_stats = line_bot_api.get_push_message_delivery_statistics(date=today_str)

        if delivery_stats.success is not None and delivery_stats.success <= 0:
            line_sent_successfully = False
            line_api_error_message = "Message sent but not delivered. User might have blocked the OA."
    
    except LineBotApiError as e:
        line_sent_successfully = False
        line_api_error_message = f"LINE API Error: {e.error.message}"
        print(line_api_error_message)
    except Exception as e:
        line_sent_successfully = False
        line_api_error_message = f"An unexpected error occurred: {str(e)}"
        print(line_api_error_message)

    # บันทึกข้อความที่ส่งลงฐานข้อมูลของเรา (ส่วนนี้ทำงานไม่ว่า LINE จะส่งสำเร็จหรือไม่)
    
    new_message = LineMessage(
        user_id=user_id,
        line_account_id=oa_id,
        message_type='text',
        message_text=message_text,
        is_outgoing=True,
        timestamp=datetime.utcnow(),
        admin_user_id=current_user.id,
        line_sent_successfully=line_sent_successfully,
        line_error_message=line_api_error_message
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
            'last_message_content': truncate_text(new_message.message_text),
            'status': line_user.status,
            'picture_url': line_user.picture_url
        }
        socketio.emit('update_conversation_list', conversation_data)

    # ส่งสถานะกลับไปให้ JavaScript พร้อมบอกว่าส่งไป LINE สำเร็จหรือไม่
    return jsonify({
        "status": "success",
        "db_saved_successfully": True,
        "line_sent_successfully": line_sent_successfully,
        "line_api_error_message": line_api_error_message,
        "id": new_message.id,
        "message_type": new_message.message_type,
        "content": new_message.message_text,
        "full_datetime": (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        "admin_email": current_user.email,
        "oa_name": new_message.line_account.name,
        "sender_type": 'admin'
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
    if 'image' not in request.files:
        return jsonify({"error": "No image part"}), 400
    
    file = request.files['image']
    user_id = request.form.get('user_id')
    oa_id = request.form.get('oa_id')

    if not all([file, user_id, oa_id]) or file.filename == '':
        return jsonify({"error": "Missing data or file"}), 400

    account = LineAccount.query.get(oa_id)
    if not account:
        return jsonify({"status": "error", "message": "OA not found"}), 404

    try:
        # 1. อัปโหลดไฟล์ไปที่ S3 และรับ URL ถาวรกลับมา
        permanent_url = s3_client.upload_fileobj(file)
        print(f"Uploaded to S3, URL: {permanent_url}")

        # 2. ส่ง URL ไปที่ LINE API
        line_bot_api = LineBotApi(account.channel_access_token)
        message_to_send = ImageSendMessage(
            original_content_url=permanent_url, 
            preview_image_url=permanent_url
        )
        line_bot_api.push_message(user_id, message_to_send)

        # 3. บันทึกประวัติลงฐานข้อมูล
        new_message = LineMessage(
            user_id=user_id,
            line_account_id=oa_id,
            message_type='image',
            message_url=permanent_url, # <-- บันทึก URL ถาวร
            is_outgoing=True,
            timestamp=datetime.utcnow(),
            admin_user_id=current_user.id
        )
        db.session.add(new_message)
        db.session.commit()

        # 4. ส่ง Event ไปยัง Client อื่นๆ
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
        
        # 5. ส่ง Response ที่สมบูรณ์กลับไปให้ผู้ส่ง
        return jsonify({
            "db_saved_successfully": True,
            "id": new_message.id,
            "sender_type": 'admin',
            "message_type": 'image',
            "content": new_message.message_url,
            "full_datetime": (new_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
            "admin_email": current_user.email,
            "oa_name": new_message.line_account.name
        })

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"db_saved_successfully": False, "db_error": str(e)}), 500
    
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
    oa_id = request.args.get("oa", type=int)
    offset = request.args.get("offset", type=int, default=0)
    limit = 10
    messages = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id).order_by(LineMessage.timestamp.desc()).offset(offset).limit(limit).all()
    messages.reverse()
    processed_messages = []
    for m in messages:
        sender_type = 'admin' if m.is_outgoing else 'customer'
        content = ""
        if m.message_type == "text": content = m.message_text
        elif m.message_type == "image": content = m.message_url
        elif m.message_type == "sticker": content = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{m.sticker_id}/ANDROID/sticker.png"
        elif m.message_type == "event": content = m.message_text
        local_timestamp = m.timestamp + timedelta(hours=7)
        message_data = {
            'id': m.id, # <-- เพิ่ม ID
            'sender_type': sender_type, 'message_type': m.message_type, 'content': content,
            'created_at': local_timestamp.strftime('%H:%M'),
            'full_datetime': local_timestamp.strftime('%d %b - %H:%M'),
            'is_close_event': "'Closed'" in content if m.message_type == "event" else False,
            'line_sent_successfully': m.line_sent_successfully,
            'line_error_message': m.line_error_message
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
                last_message_content = truncate_text(latest_message.message_text)
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
    user = LineUser.query.get_or_404(user_db_id)
    data = request.get_json()
    new_status = data.get('status')
    valid_statuses = ['read', 'deposit', 'withdraw', 'issue', 'closed']
    if not new_status or new_status not in valid_statuses:
        return jsonify({"status": "error", "message": "Invalid status"}), 400
    user.status = new_status
    log_text = f"📝 {current_user.email} changed status to '{new_status.capitalize()}'"
    log_message = LineMessage(user_id=user.user_id, line_account_id=user.line_account_id,
                              message_type='event', message_text=log_text,
                              is_outgoing=True, timestamp=datetime.utcnow())
    db.session.add(log_message)
    db.session.commit()
    latest_message = LineMessage.query.filter_by(user_id=user.user_id, line_account_id=user.line_account_id).order_by(LineMessage.timestamp.desc()).first()
    line_account = LineAccount.query.get(user.line_account_id)
    oa_name = line_account.name if line_account else "Unknown OA"
    last_message_prefix = "คุณ:" if latest_message and latest_message.is_outgoing else "ลูกค้า:"
    last_message_content = "[No messages yet]"
    if latest_message:
        if latest_message.message_type == 'text': last_message_content = truncate_text(latest_message.message_text)
        elif latest_message.message_type == 'event': last_message_content = latest_message.message_text
        else: last_message_content = f"[{latest_message.message_type.capitalize()}]"

        
    conversation_data = {
        'user_id': user.user_id, 'line_account_id': user.line_account_id,
        'display_name': user.nickname or user.display_name or f"User: {user.user_id[:12]}...",
        'oa_name': oa_name, 'last_message_prefix': last_message_prefix,
        'last_message_content': last_message_content, 'status': user.status,
        'picture_url': user.picture_url
    }
    socketio.emit('update_conversation_list', conversation_data)
    room_name = f"chat_{user.user_id}_{user.line_account_id}"
    message_data_for_socket = {
        'id': log_message.id, # <-- เพิ่ม ID
        'sender_type': 'admin', 'message_type': 'event',
        'content': log_message.message_text,
        'full_datetime': (log_message.timestamp + timedelta(hours=7)).strftime('%d %b - %H:%M'),
        'is_close_event': "'Closed'" in log_message.message_text,
        'user_id': user.user_id, 'oa_id': user.line_account_id,
        'admin_email': current_user.email, # <-- เพิ่ม admin_email
        'oa_name': user.line_account.name if user.line_account else 'System' # <-- เพิ่ม oa_name
    }
    socketio.emit('new_message', message_data_for_socket, to=room_name)
    socketio.emit('resort_sidebar', {})
    return jsonify({"status": "success", "new_status": new_status})

# app/blueprints/chats/routes.py
from flask import request, jsonify
from app.blueprints.chats import bp
from app.services import s3_client

# เพิ่มสองบรรทัดนี้ ถ้ายังไม่มี
from app.extensions import db
from app.models import LineMessage  # ← โมเดลของพี่

@bp.post("/upload")
def upload_media():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "missing file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400

    # 1) อัปโหลดขึ้น S3
    key = s3_client.upload_fileobj(f)
    url = s3_client.presigned_get_url(key, 3600)

    # 2) ถ้ามี message_id ส่งมา -> อัปเดตแถวเดิม
    msg_id = request.form.get("message_id") or request.args.get("message_id")
    updated = False
    if msg_id:
        msg = LineMessage.query.get(msg_id)
        if not msg:
            return jsonify({"ok": False, "error": f"message_id {msg_id} not found", "s3_key": key, "url": url}), 404
        msg.media_key = key
        # ถ้าอยากแท็กชนิดด้วย
        if not msg.message_type or msg.message_type == "text":
            msg.message_type = "image"  # หรือ "file" ตามชนิด
        db.session.commit()
        updated = True

    return jsonify({
        "ok": True,
        "s3_key": key,
        "url": url,
        "message_id": int(msg_id) if msg_id else None,
        "updated": updated
    }), 201

@bp.get("/media_url")
def media_url():
    key = request.args.get("key")
    if not key:
        return jsonify({"ok": False, "error": "missing key"}), 400

    url = s3_client.presigned_get_url(key, 3600)  # ลิงก์ชั่วคราว 1 ชม.
    return jsonify({"ok": True, "url": url}), 200

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