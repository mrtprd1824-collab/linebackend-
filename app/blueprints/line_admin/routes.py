from flask import render_template, redirect, url_for, request, flash , current_app
from flask_login import login_required, current_user
from app.models import LineAccount , LineMessage
from app.extensions import db
from . import bp   # ใช้ bp ที่สร้างใน __init__.py
import secrets
from sqlalchemy.orm import joinedload
from linebot import LineBotApi
from linebot.models import TextSendMessage
from app.models import LineAccount, OAGroup
from app.extensions import socketio
from flask_socketio import join_room, leave_room
from app.models import LineAccount, OAGroup

# ตรวจสอบสิทธิ์ admin
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper

# Dashboard ของ Line Accounts
@bp.route("/")
@login_required
@admin_required
def line_admin_index():
    # --- [ส่วนแก้ไขหลัก] ---
    # 1. รับค่า filter จาก URL
    selected_group_id = request.args.get('group_filter', type=int)

    # 2. สร้าง Query เริ่มต้นสำหรับ LineAccount
    # ใช้ joinedload เพื่อให้โหลดข้อมูล groups มาพร้อมกัน ลดการ query ซ้ำซ้อน
    query = LineAccount.query

    # 3. เพิ่มเงื่อนไขการกรอง
    if selected_group_id:
        # กรอง LineAccount ที่มี group.id ตรงกับที่เลือก
        query = query.join(LineAccount.groups).filter(OAGroup.id == selected_group_id)

    # 4. ดึงข้อมูล accounts ที่กรองแล้ว
    accounts = query.order_by(LineAccount.name).all()
    # --- [จบส่วนแก้ไขหลัก] ---

    # ดึงข้อมูลทั้งหมดที่จำเป็นสำหรับหน้าเว็บ
    groups = OAGroup.query.order_by(OAGroup.name).all()
    base_url = current_app.config.get("BASE_URL", request.url_root)
    base_url = base_url.rstrip("/") + "/"

    return render_template(
        "line_accounts/index.html",
        accounts=accounts,
        groups=groups,
        base_url=base_url,
        selected_group_id=selected_group_id # ส่ง ID ที่เลือกอยู่กลับไป
    )
    
# Add new Line Account
@bp.route("/add", methods=["POST"])
@login_required
@admin_required
def add_line_account():
    name = request.form["name"]
    channel_id = request.form["channel_id"]
    channel_secret = request.form["channel_secret"]
    channel_access_token = request.form["channel_access_token"]
    random_path = secrets.token_urlsafe(6)

    new_account = LineAccount(
        name=name,
        channel_id=channel_id,
        channel_secret=channel_secret,
        channel_access_token=channel_access_token,
        webhook_path=random_path,
        manager_url=request.form.get("manager_url"),
        is_active=True
    )

    # ✅ Groups
    selected_group_ids = request.form.getlist("groups")
    if selected_group_ids:
        new_account.groups = OAGroup.query.filter(OAGroup.id.in_(selected_group_ids)).all()

    db.session.add(new_account)
    db.session.commit()

    flash("Line OA added successfully!", "success")
    return redirect(url_for("line_admin.line_admin_index"))


# Edit Line Account
@bp.route("/edit/<int:id>", methods=["POST"])
@login_required
@admin_required
def edit_line_account(id):
    account = LineAccount.query.get_or_404(id)

    account.name = request.form["name"]
    account.channel_id = request.form["channel_id"]
    account.channel_secret = request.form["channel_secret"]

    # ถ้าไม่ใส่อะไรในฟิลด์ Access Token → คงค่าเดิม
    if request.form["channel_access_token"].strip():
        account.channel_access_token = request.form["channel_access_token"]

    account.manager_url = request.form.get("manager_url")

    # ✅ Groups
    selected_group_ids = request.form.getlist("groups")
    account.groups = OAGroup.query.filter(OAGroup.id.in_(selected_group_ids)).all()

    db.session.commit()
    flash("Line OA updated successfully!", "success")
    return redirect(url_for("line_admin.line_admin_index"))


# Delete Line Account
@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_line_account(id):
    account = LineAccount.query.get_or_404(id)
    db.session.delete(account)
    db.session.commit()
    flash("Line OA deleted successfully!", "success")
    return redirect(url_for("line_admin.line_admin_index"))

# Line message (with filter)
@bp.route("/line_messages")
@login_required
def line_messages_index():
    if not current_user.is_admin:
        abort(403)

    accounts = LineAccount.query.all()
    selected_account_id = request.args.get("account_id", type=int)

    query = LineMessage.query.order_by(LineMessage.timestamp.desc())
    if selected_account_id:
        query = query.filter_by(line_account_id=selected_account_id)

    messages = query.all()

    return render_template(
        "line_messages/index.html",
        messages=messages,   # << ส่ง messages ไปแล้ว
        accounts=accounts,
        selected_account_id=selected_account_id
    )


@bp.route("/line_messages/reply/<int:message_id>", methods=["POST"])
@login_required
def reply_message(message_id):
    import os, secrets
    from datetime import datetime, timedelta, timezone
    from werkzeug.utils import secure_filename
    from linebot.models import TextSendMessage, ImageSendMessage, StickerSendMessage

    THAI_TZ = timezone(timedelta(hours=7))

    msg = LineMessage.query.get_or_404(message_id)
    account = LineAccount.query.get_or_404(msg.line_account_id)
    next_url = request.args.get("next")

    reply_type = request.form.get("reply_type", "text")
    line_bot_api = LineBotApi(account.channel_access_token)

    # เตรียมบันทึก outgoing message
    new_out = LineMessage(
        line_account_id=msg.line_account_id,
        user_id=msg.user_id,
        timestamp=datetime.now(THAI_TZ),
        is_outgoing=True
    )

    try:
        if reply_type == "text":
            reply_text = (request.form.get("reply_text") or "").strip()
            if not reply_text:
                flash("กรุณากรอกข้อความก่อนส่ง", "danger")
                return redirect(url_for("line_admin.line_messages_index"))
            line_bot_api.push_message(msg.user_id, TextSendMessage(text=reply_text))
            new_out.message_type = "text"
            new_out.message_text = reply_text

        elif reply_type == "image":
            file = request.files.get("image_file")
            if not file or file.filename == "":
                flash("กรุณาเลือกไฟล์รูปภาพ", "danger")
                return redirect(url_for("line_admin.line_messages_index"))

            upload_dir = os.path.join(current_app.root_path, "..", "static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)

            safe_name = secure_filename(file.filename)
            filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
            save_path = os.path.join(upload_dir, filename)
            file.save(save_path)

            base_url = current_app.config.get("BASE_URL", request.url_root).rstrip("/") + "/"
            public_url = base_url + f"static/uploads/{filename}"

            line_bot_api.push_message(
                msg.user_id,
                ImageSendMessage(original_content_url=public_url, preview_image_url=public_url)
            )
            new_out.message_type = "image"
            new_out.message_url = f"/static/uploads/{filename}"

        elif reply_type == "sticker":
            package_id = request.form.get("package_id")
            sticker_id = request.form.get("sticker_id")
            if not (package_id and sticker_id):
                flash("กรุณากรอก package_id และ sticker_id", "danger")
                return redirect(url_for("line_admin.line_messages_index"))

            line_bot_api.push_message(
                msg.user_id,
                StickerSendMessage(package_id=package_id, sticker_id=sticker_id)
            )
            new_out.message_type = "sticker"
            new_out.package_id = package_id
            new_out.sticker_id = sticker_id

        else:
            flash("ชนิดข้อความไม่ถูกต้อง", "danger")
            return redirect(url_for("line_admin.line_messages_index"))

        db.session.add(new_out)
        db.session.commit()
        flash("ส่งข้อความเรียบร้อยแล้ว", "success")

        socketio.emit("new_message", {
            "id": new_out.id,
            "sender_type": "admin",
            "message_type": new_out.message_type,
            "content": new_out.message_text if new_out.message_type == "text" else (
                new_out.message_url if new_out.message_type == "image" else
                f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{new_out.sticker_id}/ANDROID/sticker.png"
            ),
            "created_at": new_out.timestamp.strftime("%H:%M")
        }, room=new_out.user_id)

        print("emit to room", new_out.user_id)

    except Exception as e:
        current_app.logger.exception("Reply failed")
        flash(f"ส่งข้อความล้มเหลว: {e}", "danger")

    return redirect(next_url or url_for("line_admin.line_messages_index"))

@socketio.on("join")
def handle_join(data):
    print("join event received:", data)  # debug
    user_id = data.get("user_id")
    if user_id:
        join_room(user_id)
        print(f"User joined room {user_id}")


@socketio.on("connect")
def on_connect():
    print("⚡ client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("⚡ client disconnected")        
                    

