from flask import Blueprint, request, jsonify
from app.models import db, Tag, LineUser
from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required

# สร้าง Blueprint ที่ชื่อว่า 'tags'
bp = Blueprint('tags', __name__, url_prefix='/api/tags')

# API สำหรับจัดการ Tags
@bp.route('', methods=['GET'])
def get_tags():
    """API สำหรับดึงรายชื่อ Tag ทั้งหมด"""
    tags = Tag.query.order_by(Tag.name).all()
    # แปลงข้อมูล Tag objects ให้เป็น JSON ที่ Frontend ใช้งานได้
    tags_list = [{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in tags]
    return jsonify(tags_list)

# API สำหรับสร้าง Tag ใหม่
@bp.route('', methods=['POST'])
def create_tag():
    """API สำหรับสร้าง Tag ใหม่"""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Missing tag name'}), 400

    # ตรวจสอบว่ามี Tag ชื่อนี้อยู่แล้วหรือไม่ (ป้องกันชื่อซ้ำ)
    if Tag.query.filter_by(name=data['name']).first():
        return jsonify({'error': 'Tag with this name already exists'}), 409

    # สร้าง Tag ใหม่และบันทึกลงฐานข้อมูล
    new_tag = Tag(
        name=data['name'],
        color=data.get('color', '#6c757d') # ถ้าไม่ได้ส่งสีมา ให้ใช้สีเทาเป็นค่าเริ่มต้น
    )
    db.session.add(new_tag)
    db.session.commit()

    return jsonify({'id': new_tag.id, 'name': new_tag.name, 'color': new_tag.color}), 201

# API สำหรับติดแท็กให้ผู้ใช้
@bp.route('/<int:user_id>/assign', methods=['POST'])
def assign_tag_to_user(user_id):
    """API สำหรับติดแท็กให้ผู้ใช้"""
    data = request.get_json()
    tag_id = data.get('tag_id')

    if not tag_id:
        return jsonify({'error': 'Missing tag_id'}), 400

    user = LineUser.query.get_or_404(user_id)
    tag = Tag.query.get_or_404(tag_id)

    # ตรวจสอบว่าผู้ใช้ยังไม่มีแท็กนี้ (ป้องกันการเพิ่มซ้ำ)
    if tag not in user.tags:
        user.tags.append(tag)
        db.session.commit()
    
    return jsonify({'success': True, 'message': f'Tag "{tag.name}" added to user {user.id}'})

# API สำหรับลบแท็กออกจากผู้ใช้
@bp.route('/<int:user_id>/remove/<int:tag_id>', methods=['DELETE'])
def remove_tag_from_user(user_id, tag_id):
    """API สำหรับลบแท็กออกจากผู้ใช้"""
    user = LineUser.query.get_or_404(user_id)
    tag = Tag.query.get_or_404(tag_id)

    # ตรวจสอบว่าผู้ใช้มีแท็กนี้อยู่จริง
    if tag in user.tags:
        user.tags.remove(tag)
        db.session.commit()

    return jsonify({'success': True, 'message': f'Tag "{tag.name}" removed from user {user.id}'})

@bp.route('/manage')
@login_required
def manage_tags_page():
    """Route สำหรับแสดงหน้า 'Manage Tags'"""
    all_tags = Tag.query.order_by(Tag.name).all()
    return render_template('tags/manage_tags.html', tags=all_tags)

@bp.route('/add', methods=['POST'])
@login_required
def add_tag():
    """Route สำหรับรับข้อมูลจากฟอร์มเพื่อสร้าง Tag ใหม่"""
    name = request.form.get('name')
    color = request.form.get('color')

    if not name or not color:
        flash('Tag name and color are required.', 'danger')
        return redirect(url_for('tags.manage_tags_page'))

    if Tag.query.filter_by(name=name).first():
        flash('A tag with this name already exists.', 'warning')
        return redirect(url_for('tags.manage_tags_page'))

    new_tag = Tag(name=name, color=color)
    db.session.add(new_tag)
    db.session.commit()
    flash('New tag created successfully!', 'success')
    return redirect(url_for('tags.manage_tags_page'))

@bp.route('/<int:tag_id>/delete', methods=['POST'])
@login_required
def delete_tag(tag_id):
    """Route สำหรับลบ Tag"""
    tag_to_delete = Tag.query.get_or_404(tag_id)
    db.session.delete(tag_to_delete)
    db.session.commit()
    flash(f'Tag "{tag_to_delete.name}" has been deleted.', 'success')
    return redirect(url_for('tags.manage_tags_page'))