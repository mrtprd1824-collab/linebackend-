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
from sqlalchemy.orm import joinedload
from linebot import LineBotApi
from linebot.models import TextSendMessage , ImageSendMessage , StickerSendMessage
from linebot.exceptions import LineBotApiError
from sqlalchemy import or_
from app.models import User, LineUser, LineAccount, LineMessage, QuickReply, OAGroup, Sticker
import traceback
from app.extensions import socketio
from app.blueprints.chats import bp
from app.services import s3_client

# ---- Helper Functions ----

def format_message_for_api(message):
    """แปลง LineMessage object เป็น Dictionary สำหรับส่งออกไปเป็น JSON"""
    sender_type = 'admin' if message.is_outgoing else 'customer'
    content = ""
    is_close_event = False

    if message.message_type == "text":
        content = message.message_text
    elif message.message_type == "image":
        content = message.message_url
    elif message.message_type == "sticker":
        content = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{message.sticker_id}/ANDROID/sticker.png"
    elif message.message_type == "event":
        content = message.message_text
        if "'Closed'" in content:
            is_close_event = True

    local_timestamp = message.timestamp + timedelta(hours=7)
        
    message_data = {
        'id': message.id,
        'sender_type': sender_type,
        'message_type': message.message_type,
        'content': content,
        'created_at': local_timestamp.strftime('%H:%M'),
        'full_datetime': local_timestamp.strftime('%d %b - %H:%M'),
        'is_close_event': is_close_event,
        'line_sent_successfully': message.line_sent_successfully,
        'line_error_message': message.line_error_message
    }

    if message.is_outgoing and message.admin:
        message_data['admin_email'] = message.admin.email
        message_data['oa_name'] = message.line_account.name if message.line_account else 'N/A'
        
    return message_data

def truncate_text(text, length=10):
    if text and len(text) > length:
        return text[:length] + '...'
    return text

def truncate_text(text, length=10):
    """ตัดข้อความและต่อท้ายด้วย '...' ถ้ามันยาวเกินที่กำหนด"""
    if text and len(text) > length:
        return text[:length] + '...'
    return text

# ---- Routes ----

@bp.route("/")
@login_required
def index():
    try:
        all_groups = OAGroup.query.order_by(OAGroup.name).all()
        selected_group_ids = session.get("active_group_ids", [])
        status_filter = request.args.get('status_filter', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 20

        subquery = db.session.query(
            LineMessage.user_id,
            LineMessage.line_account_id,
            func.max(LineMessage.timestamp).label('max_timestamp')
        ).group_by(LineMessage.user_id, LineMessage.line_account_id).subquery()

        # [FIXED] เพิ่ม Eager Loading ด้วย options(joinedload(...))
        query = db.session.query(
            LineMessage, LineUser
        ).join(
            subquery,
            (LineMessage.user_id == subquery.c.user_id) &
            (LineMessage.line_account_id == subquery.c.line_account_id) &
            (LineMessage.timestamp == subquery.c.max_timestamp)
        ).join(
            LineUser,
            (LineMessage.user_id == LineUser.user_id) &
            (LineMessage.line_account_id == LineUser.line_account_id)
        ).options(
            joinedload(LineMessage.line_account), # <-- บอกให้โหลด LineAccount มาพร้อมกัน
            joinedload(LineMessage.admin)         # <-- บอกให้โหลด Admin มาพร้อมกัน (ถ้ามี)
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
            sort_order.asc(),
            subquery.c.max_timestamp.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

        users_with_messages = pagination.items
        
        # --- [OPTIMIZED] แก้ปัญหา N+1 Query ---
        user_info_for_unread = [
            (user.user_id, user.line_account_id, user.last_read_timestamp)
            for msg, user in users_with_messages
        ]
        
        unread_counts_map = {}
        if user_info_for_unread:
            conditions = []
            for uid, l_acc_id, last_read in user_info_for_unread:
                base_condition = (
                    (LineMessage.user_id == uid) &
                    (LineMessage.line_account_id == l_acc_id) &
                    (LineMessage.is_outgoing == False)
                )
                if last_read:
                    base_condition = base_condition & (LineMessage.timestamp > last_read)
                conditions.append(base_condition)

            if conditions:
                query_for_counts = db.session.query(
                    LineMessage.user_id, 
                    LineMessage.line_account_id,
                    func.count(LineMessage.id)
                ).filter(or_(*conditions)).group_by(LineMessage.user_id, LineMessage.line_account_id).all()
                
                unread_counts_map = {(uid, l_id): count for uid, l_id, count in query_for_counts}
        # --- จบส่วน Optimized ---
                
        conversations = []
        for msg, user in users_with_messages:
            unread_count = unread_counts_map.get((user.user_id, user.line_account_id), 0)
            
            # --- [เพิ่มส่วนแก้ไข Timezone] ---
            # 1. ทำให้ Python รู้ว่าเวลาที่ดึงมาเป็น UTC
            aware_timestamp = msg.timestamp.replace(tzinfo=timezone.utc)
            # 2. แปลงเป็นตัวเลข Unix Timestamp ที่ถูกต้อง
            correct_timestamp = aware_timestamp.timestamp()
            # --------------------------------

            conversations.append({
                "message": msg,
                "user": user,
                "unread_count": unread_count,
                # 3. เพิ่ม key ใหม่เข้าไปในข้อมูล
                "last_unread_timestamp": correct_timestamp ,
                "tags": [{'name': tag.name, 'color': tag.color} for tag in user.tags]
            })
        
        return render_template(
            "chats/index.html",
            conversations=conversations,
            pagination=pagination,
            all_groups=all_groups,
            selected_group_ids=selected_group_ids,
            status_filter=status_filter
        )
    except Exception as e:
        db.session.rollback() # <--- เพิ่ม Rollback เมื่อเกิด Exception
        current_app.logger.error(f"Error in chats.index: {e}")
        traceback.print_exc()
        abort(500, "An error occurred while loading chats.")


@bp.route("/<user_id>", endpoint="show")
@login_required
def show(user_id):
    oa_id = request.args.get("oa", type=int)
    if not oa_id:
        abort(400, "Bad Request: Missing 'oa' parameter in the URL.")
    account = LineAccount.query.get_or_404(oa_id)

    offset = request.args.get("offset", 0, type=int)
    limit = 10

    query = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id)
    total_messages = query.count()

    messages = (
        query.order_by(LineMessage.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    messages = list(reversed(messages))

    processed_messages = [format_message_for_api(m) for m in messages]
    quick_replies = QuickReply.query.order_by(QuickReply.created_at.desc()).all()
    line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first()

    return render_template(
        "chats/show.html",
        account=account,
        user_id=user_id,
        messages=processed_messages,
        oa_id=oa_id,
        offset=offset,
        limit=limit,
        total_messages=total_messages,
        quick_replies=quick_replies,
        line_user=line_user
    )

@bp.route("/api/messages/<user_id>")
@login_required
def get_messages_for_user(user_id):
    oa_id = request.args.get("oa", type=int)
    frozen_time = request.args.get('frozen_time', None)

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

    if status_was_changed:
        latest_message = LineMessage.query.filter_by(user_id=line_user.user_id, line_account_id=line_user.line_account_id).order_by(LineMessage.timestamp.desc()).first()
        line_account = LineAccount.query.get(line_user.line_account_id)
        oa_name = line_account.name if line_account else "Unknown OA"
        last_message_prefix = "คุณ:" if latest_message and latest_message.is_outgoing else "ลูกค้า:"
        last_message_content = "[No messages yet]"
        if latest_message:
            if latest_message.message_type == 'text': last_message_content = truncate_text(latest_message.message_text)
            elif latest_message.message_type == 'event': last_message_content = latest_message.message_text
            else: last_message_content = f"[{latest_message.message_type.capitalize()}]"

        conversation_data = {
            'user_id': line_user.user_id,
            'line_account_id': line_user.line_account_id,
            'display_name': line_user.nickname or line_user.display_name or f"User: {line_user.user_id[:12]}...",
            'oa_name': oa_name,
            'last_message_prefix': last_message_prefix,
            'last_message_content': last_message_content,
            'status': line_user.status,
            'picture_url': line_user.picture_url,
            'frozen_time': frozen_time
        }
        socketio.emit('resort_sidebar', conversation_data)

    user_tags = [{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in line_user.tags]
    total_messages = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id).count()
    messages_query = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id).order_by(LineMessage.timestamp.desc()).limit(20).all()
    messages_query.reverse()
    processed_messages = [format_message_for_api(m) for m in messages_query]
    response_data = {
        "user": {
            "db_id": line_user.id, 
            "display_name": line_user.display_name, 
            "nickname": line_user.nickname or '', 
            "phone": line_user.phone or '', 
            "note": line_user.note or '', 
            "status": line_user.status, 
            "is_blocked": line_user.is_blocked,
            "tags": user_tags,
            "picture_url": line_user.picture_url
        },
        "account": {"id": account.id, "name": account.name, "manager_url": account.manager_url},
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
    line_user = LineUser.query.filter_by(user_id=user_id, line_account_id=oa_id).first()

    if not account or not line_user:
        return jsonify({"status": "error", "message": "OA or User not found"}), 404

    line_sent_successfully = True
    line_api_error_message = None

    if line_user.is_blocked:
        line_sent_successfully = False
        line_api_error_message = "Message not sent: This user has blocked the OA."
    else:
        try:
            line_bot_api = LineBotApi(account.channel_access_token)
            message_to_send = TextSendMessage(text=message_text)
            line_bot_api.push_message(user_id, message_to_send)
        except LineBotApiError as e:
            line_sent_successfully = False
            line_api_error_message = f"LINE API Error: {e.error.message}"
        except Exception as e:
            line_sent_successfully = False
            line_api_error_message = f"An unexpected error occurred: {str(e)}"

    line_user.last_message_at = datetime.utcnow()

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
    message_data_for_socket = format_message_for_api(new_message)
    message_data_for_socket.update({'user_id': user_id, 'oa_id': int(oa_id)})
    socketio.emit('new_message', message_data_for_socket, to=room_name)

    conversation_data = {
        'user_id': user_id,
        'line_account_id': int(oa_id),
        'display_name': line_user.nickname or line_user.display_name or f"User: {user_id[:12]}...",
        'oa_name': new_message.line_account.name,
        'last_message_prefix': "คุณ:",
        'last_message_content': truncate_text(new_message.message_text),
        'status': line_user.status,
        'picture_url': line_user.picture_url
    }
    socketio.emit('update_conversation_list', conversation_data)

    response_data = format_message_for_api(new_message)
    response_data.update({
        "status": "success",
        "db_saved_successfully": True,
        "line_sent_successfully": line_sent_successfully,
        "line_api_error_message": line_api_error_message,
    })
    return jsonify(response_data)


@bp.route('/user/update/<int:id>', methods=['POST'])
@login_required
def update_details(id):
    user = User.query.get_or_404(id)
    user.real_name = request.form.get('real_name')
    user.phone_number = request.form.get('phone_number')
    user.note = request.form.get('note')
    db.session.commit()
    flash('User details updated successfully!', 'success')
    next_url = request.args.get('next')
    return redirect(next_url or url_for('chats.index'))

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
        permanent_url = s3_client.upload_fileobj(file)
        
        line_bot_api = LineBotApi(account.channel_access_token)
        message_to_send = ImageSendMessage(
            original_content_url=permanent_url, 
            preview_image_url=permanent_url
        )
        line_bot_api.push_message(user_id, message_to_send)

        new_message = LineMessage(
            user_id=user_id,
            line_account_id=oa_id,
            message_type='image',
            message_url=permanent_url,
            is_outgoing=True,
            timestamp=datetime.utcnow(),
            admin_user_id=current_user.id
        )
        db.session.add(new_message)
        db.session.commit()

        room_name = f"chat_{user_id}_{oa_id}"
        message_data_for_socket = format_message_for_api(new_message)
        message_data_for_socket.update({'user_id': user_id, 'oa_id': int(oa_id)})
        socketio.emit('new_message', message_data_for_socket, to=room_name)
        
        response_data = format_message_for_api(new_message)
        response_data.update({"db_saved_successfully": True})
        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"db_saved_successfully": False, "db_error": str(e)}), 500
    
@bp.route("/api/send_sticker", methods=["POST"])
@login_required
def send_sticker():
    data = request.get_json()
    user_id = data.get('user_id')
    package_id = data.get('package_id')
    sticker_id = data.get('sticker_id')
    oa_id = data.get('oa_id')

    if not all([user_id, oa_id, package_id, sticker_id]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    account = LineAccount.query.get(oa_id)
    if not account:
        return jsonify({"status": "error", "message": "OA not found"}), 404

    try:
        line_bot_api = LineBotApi(account.channel_access_token)
        message_to_send = StickerSendMessage(package_id=package_id, sticker_id=sticker_id)
        line_bot_api.push_message(user_id, message_to_send)
    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to send sticker via LINE"}), 500

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
    message_data_for_socket = format_message_for_api(new_message)
    message_data_for_socket.update({'user_id': user_id, 'oa_id': int(oa_id)})
    socketio.emit('new_message', message_data_for_socket, to=room_name)

    response_data = format_message_for_api(new_message)
    response_data.update({"status": "success", "db_saved_successfully": True})
    return jsonify(response_data)


@bp.route('/api/quick_replies/<int:oa_id>')
@login_required
def get_quick_replies(oa_id):
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
    if user.nickname != new_nickname:
        log_messages.append(f"📝 {current_user.email} changed Nickname to '{new_nickname}'")
        user.nickname = new_nickname
    if user.phone != new_phone:
        log_messages.append(f"📝 {current_user.email} changed Phone to '{new_phone}'")
        user.phone = new_phone
    if user.note != new_note:
        log_messages.append(f"📝 {current_user.email} changed Note")
        user.note = new_note

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

@bp.route('/api/stickers')
@login_required
def api_stickers():
    try:
        stickers = Sticker.query.all()
        sticker_list = [
            {'packageId': s.packageId, 'stickerId': s.stickerId} 
            for s in stickers
        ]
        return jsonify(sticker_list)
    except Exception as e:
        return jsonify({"error": "Could not fetch stickers"}), 500
    
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

    return Response(
        chat_history_text,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=chat_{user_id}.txt"}
    )    

@bp.route("/<user_id>/more")
@login_required
def load_more(user_id):
    oa_id = request.args.get("oa", type=int)
    offset = request.args.get("offset", type=int, default=0)
    limit = 10
    messages = LineMessage.query.filter_by(user_id=user_id, line_account_id=oa_id).order_by(LineMessage.timestamp.desc()).offset(offset).limit(limit).all()
    messages.reverse()
    
    processed_messages = [format_message_for_api(m) for m in messages]
    
    return jsonify({"messages": processed_messages})

@bp.route('/api/search_conversations')
@login_required
def search_conversations():
    query_term = request.args.get('q', '').strip()
    selected_group_ids = session.get("active_group_ids", [])

    if not query_term:
        return jsonify([])

    user_query = LineUser.query.filter(
        or_(
            LineUser.nickname.ilike(f"%{query_term}%"),
            LineUser.phone.ilike(f"%{query_term}%"),
            LineUser.user_id.ilike(f"%{query_term}%")
        )
    )

    if selected_group_ids:
        user_query = user_query.join(LineAccount).filter(LineAccount.groups.any(OAGroup.id.in_(selected_group_ids)))

    found_users = user_query.limit(20).all()

    results = []
    for user in found_users:
        latest_message = LineMessage.query.filter_by(
            user_id=user.user_id,
            line_account_id=user.line_account_id
        ).order_by(LineMessage.timestamp.desc()).first()

        if latest_message:
            if latest_message.is_outgoing:
                last_message_prefix = "คุณ:"
            else:
                last_message_prefix = "ลูกค้า:"
            
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
                'is_read': latest_message.is_outgoing,
                'picture_url': user.picture_url,
                'status': user.status
            })

    return jsonify(results)

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
    message_data_for_socket = format_message_for_api(log_message)
    message_data_for_socket.update({
        'user_id': user.user_id, 'oa_id': user.line_account_id,
    })
    socketio.emit('new_message', message_data_for_socket, to=room_name)
    socketio.emit('resort_sidebar', conversation_data)
    return jsonify({"status": "success", "new_status": new_status})

@bp.post("/upload")
def upload_media():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "missing file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400

    key = s3_client.upload_fileobj(f)
    url = s3_client.presigned_get_url(key, 3600)

    msg_id = request.form.get("message_id") or request.args.get("message_id")
    updated = False
    if msg_id:
        msg = LineMessage.query.get(msg_id)
        if not msg:
            return jsonify({"ok": False, "error": f"message_id {msg_id} not found", "s3_key": key, "url": url}), 404
        msg.media_key = key
        if not msg.message_type or msg.message_type == "text":
            msg.message_type = "image"
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

    url = s3_client.presigned_get_url(key, 3600)
    return jsonify({"ok": True, "url": url}), 200

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
