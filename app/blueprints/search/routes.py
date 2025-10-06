from flask import render_template, request, jsonify
from flask_login import login_required
from sqlalchemy import or_
from datetime import datetime, timedelta

from . import bp # import bp จาก __init__.py ในโฟลเดอร์เดียวกัน
from app.models import db, LineUser, Tag , LineAccount

import pytz
from datetime import datetime, timedelta

import io
import csv
from flask import Response

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
    
        # สร้าง timezone object เตรียมไว้
    utc_zone = pytz.utc
    bkk_zone = pytz.timezone('Asia/Bangkok')

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
        naive_start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        bkk_start_time = bkk_zone.localize(naive_start_date)
        utc_start_time = bkk_start_time.astimezone(pytz.utc)
        query = query.filter(LineUser.last_message_at >= utc_start_time)
    
    if end_date_str:
        naive_end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        bkk_end_time = bkk_zone.localize(naive_end_date)
        utc_end_time = bkk_end_time.astimezone(pytz.utc)
        query = query.filter(LineUser.last_message_at < utc_end_time)

    pagination = query.order_by(LineUser.last_seen_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    users = pagination.items

    
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


@bp.route('/api/search/users/export')
@login_required
def export_users():
    """API สำหรับ Export ผลการค้นหาทั้งหมดเป็น CSV"""
    # 1. คัดลอก Logic การรับค่าและสร้าง Query ทั้งหมดมาจากฟังก์ชัน search_users_api()
    # เพื่อให้แน่ใจว่าเงื่อนไขการกรองจะเหมือนกันทุกประการ
    query_term = request.args.get('q', '').strip()
    tag_ids_str = request.args.get('tags', '')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    oa_id = request.args.get('oa_id', type=int)

    query = LineUser.query.join(LineAccount, LineUser.line_account_id == LineAccount.id)

    if query_term:
        search_pattern = f"%{query_term}%"
        query = query.filter(or_(LineUser.display_name.ilike(search_pattern), LineUser.nickname.ilike(search_pattern), LineUser.phone.ilike(search_pattern), LineUser.user_id.ilike(search_pattern)))
    if tag_ids_str:
        try:
            tag_ids = [int(id) for id in tag_ids_str.split(',')]
            query = query.join(LineUser.tags).filter(Tag.id.in_(tag_ids))
        except ValueError: pass
    if oa_id:
        query = query.filter(LineUser.line_account_id == oa_id)
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(LineUser.last_message_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(LineUser.last_message_at < end_date)

    # 2. ดึงข้อมูล "ทั้งหมด" โดยไม่ใช้ .paginate()
    users = query.order_by(LineUser.last_message_at.desc()).all()

    # 3. สร้างไฟล์ CSV ใน Memory
    output = io.StringIO()
    writer = csv.writer(output)

    # เขียน Header
    header = ['Tag', 'Name/Nickname', 'Phone', 'User ID', 'Line OA', 'Last Seen (Bangkok)']
    writer.writerow(header)

    # เขียนข้อมูลแต่ละแถว
    utc_zone = pytz.utc
    bkk_zone = pytz.timezone('Asia/Bangkok')
    for user in users:
        tags_str = ', '.join([tag.name for tag in user.tags])
        last_seen_str = 'N/A'
        if user.last_message_at:
            bkk_time = user.last_message_at.replace(tzinfo=utc_zone).astimezone(bkk_zone)
            last_seen_str = bkk_time.strftime('%Y-%m-%d %H:%M')

        row = [
            tags_str,
            user.nickname or user.display_name,
            user.phone,
            user.user_id,
            user.line_account.name,
            last_seen_str
        ]
        writer.writerow(row)

    output.seek(0) # กลับไปที่จุดเริ่มต้นของไฟล์ใน memory

    # 4. ส่งไฟล์ CSV กลับไปให้ผู้ใช้ดาวน์โหลด
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=customers_export.csv"}
    )