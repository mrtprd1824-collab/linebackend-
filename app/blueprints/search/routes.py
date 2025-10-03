from flask import render_template, request, jsonify
from flask_login import login_required
from sqlalchemy import or_
from datetime import datetime, timedelta

from . import bp # import bp จาก __init__.py ในโฟลเดอร์เดียวกัน
from app.models import db, LineUser, Tag , LineAccount

import pytz
from datetime import datetime, timedelta

@bp.route('/search_page')
@login_required
def search_page():
    """Route สำหรับแสดงหน้าเว็บสำหรับค้นหา"""
    all_line_accounts = LineAccount.query.order_by(LineAccount.name).all()
    return render_template('chats/search.html', all_line_accounts=all_line_accounts)


# ในไฟล์ app/blueprints/search/routes.py

@bp.route('/api/search/users')
@login_required
def search_users_api():
    """API สำหรับค้นหาและกรอง LineUser (เวอร์ชันอัปเดต)"""
    page = request.args.get('page', 1, type=int)
    query_term = request.args.get('q', '').strip()
    tag_ids_str = request.args.get('tags', '')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    oa_id = request.args.get('oa_id', type=int)

    # ★★★ สร้าง Query เริ่มต้นที่ Join กับ LineAccount ไว้เลย ★★★
    # เพื่อให้สามารถดึงชื่อ OA มาใช้ได้เสมอ
    query = LineUser.query.join(LineAccount, LineUser.line_account_id == LineAccount.id)

    # --- กรองด้วยข้อความ ---
    if query_term:
        search_pattern = f"%{query_term}%"
        query = query.filter(
            or_(
                LineUser.display_name.ilike(search_pattern),
                LineUser.nickname.ilike(search_pattern),
                LineUser.phone.ilike(search_pattern),
                LineUser.user_id.ilike(search_pattern)
            )
        )

    # --- กรองด้วย Tag ---
    if tag_ids_str:
        try:
            tag_ids = [int(id) for id in tag_ids_str.split(',')]
            # ต้อง join กับ relationship 'tags'
            query = query.join(LineUser.tags).filter(Tag.id.in_(tag_ids))
        except ValueError:
            return jsonify({"error": "Invalid tag IDs format"}), 400

    # --- กรองด้วย Line OA ---
    if oa_id:
        query = query.filter(LineUser.line_account_id == oa_id)

    # --- กรองด้วยวันที่ติดต่อล่าสุด ---
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(LineUser.last_seen_at >= start_date)
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(LineUser.last_seen_at < end_date)

    # --- ส่วนที่เหลือเหมือนเดิม ---
    pagination = query.order_by(LineUser.last_seen_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    users = pagination.items

    # สร้าง timezone object เตรียมไว้
    utc_zone = pytz.utc
    bkk_zone = pytz.timezone('Asia/Bangkok')
    
    results = []
    for user in users:
        last_seen_str = 'N/A'
        if user.last_message_at:
            utc_time = user.last_message_at.replace(tzinfo=utc_zone)
            bkk_time = utc_time.astimezone(bkk_zone)
            last_seen_str = bkk_time.strftime('%Y-%m-%d %H:%M')

        results.append({
            'id': user.id, 'user_id': user.user_id,
            'line_account_id': user.line_account_id,
            'display_name': user.display_name, 'nickname': user.nickname,
            'phone': user.phone or '',
            'line_oa_name': user.line_account.name,
            'last_seen_at': last_seen_str,
            'tags': [{'name': tag.name, 'color': tag.color} for tag in user.tags]
        })

    return jsonify({
        'users': results,
        'pagination': {
            'total_pages': pagination.pages,
            'current_page': pagination.page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })
