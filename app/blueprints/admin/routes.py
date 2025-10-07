from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash , jsonify 
from flask_login import login_required, current_user
from app.models import User
from app.extensions import db
from datetime import timedelta
from app.models import LineAccount
from app.services.oa_checker import check_single_oa_status , check_single_oa_webhook
from app import socketio
from datetime import timedelta
from app import socketio, create_app
from flask_socketio import join_room


bp = Blueprint("admin", __name__, url_prefix="/admin")

# decorator สำหรับเช็คสิทธิ์ admin (ฉบับแก้ไขสมบูรณ์)
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        is_admin_check = False # กำหนดค่าเริ่มต้น
        if current_user.is_authenticated:
            # ใช้ .lower() เพื่อแปลง role เป็นตัวพิมพ์เล็กก่อนเปรียบเทียบ
            is_admin_check = current_user.role.lower() == 'admin' if current_user.role else False
        
        if not current_user.is_authenticated or not is_admin_check:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("auth.dashboard")) 
        
        # ★★★ แก้ไข angs เป็น args ตรงนี้ครับ ★★★
        return func(*args, **kwargs)
    return decorated_view

# Users to manage_users
@bp.route("/users")
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template("manage_users.html", users=users)

# add users
@bp.route("/users/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get('role')

    if User.query.filter_by(email=email).first():
        flash('This email is already registered.', 'warning')
        return redirect(url_for('admin.manage_users'))
    
    new_user = User(
        email=email,
        role=role
    )

    if role == 'admin':
        new_user.is_admin = True
    else:
        new_user.is_admin = False

    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.commit()
    flash('User added successfully!', 'success')
    return redirect(url_for('admin.manage_users'))

@bp.route('/users/toggle-active/<int:user_id>', methods=['POST'])
@login_required
@admin_required 
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    # สลับค่า True/False
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User "{user.email}" status has been updated.', 'success')
    return jsonify({'success': True, 'is_active': user.is_active})


# ★★★ เพิ่ม 2: Route สำหรับแก้ไขข้อมูล User ★★★
@bp.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('password')
    new_role = request.form.get('role')

    if new_password:
        # สมมติว่าคุณมี method .set_password() ใน Model User สำหรับ hash รหัสผ่าน
        user.set_password(new_password)
        flash('Password updated successfully.', 'success')

    if new_role and new_role in ['Admin', 'User']: # ตรวจสอบค่า Role ที่ส่งมา
        user.role = new_role
        flash('Role updated successfully.', 'success')
    
    db.session.commit()
    return redirect(url_for('admin.manage_users')) # กลับไปที่หน้ารายชื่อ User

# Delete Users
@bp.route('/users/delete/<int:user_id>', methods=['POST']) # <--- [เพิ่ม] ส่วนนี้เข้าไป
@login_required
@admin_required
def delete_user(user_id):
    # ป้องกันไม่ให้แอดมินลบตัวเอง
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('admin.manage_users'))

    user_to_delete = User.query.get_or_404(user_id)
    
    db.session.delete(user_to_delete)
    db.session.commit()
    
    flash(f"User {user_to_delete.email} has been deleted.", "success")
    return redirect(url_for('admin.manage_users'))

@bp.route("/debug-db")
def debug_db_connection():
    try:
        # ลองส่ง query ง่ายๆ ไปยังฐานข้อมูล
        db.session.execute(db.text('SELECT 1'))
        return "<h1>SUCCESS: Database connection is working correctly!</h1>"
    except Exception as e:
        # ถ้าเกิด Error ให้แสดง Error นั้นออกมา
        return f"<h1>ERROR: Database connection failed.</h1><p>Error details: {e}</p>"
    

@bp.route('/oa-health-check')
@login_required
def oa_health_check_page():
    accounts = LineAccount.query.order_by(LineAccount.is_active.asc(), LineAccount.id.asc()).all()
    return render_template('admin/oa_health_check.html', accounts=accounts, timedelta=timedelta)

# --- เราจะกลับมาใช้ API Endpoint แบบเดิม ---
@bp.route('/api/run-oa-check', methods=['POST'])
@login_required
def run_oa_check_api():
    try:
        all_accounts = LineAccount.query.all()
        for acc in all_accounts:
            token_is_ok, token_message = check_single_oa_status(acc)
            webhook_is_ok, webhook_message = check_single_oa_webhook(acc)

            if token_is_ok and webhook_is_ok:
                acc.is_active = True
                acc.last_check_status_message = "OK"
            else:
                acc.is_active = False
                error_details = []
                if not token_is_ok: error_details.append(f"Token: {token_message}")
                if not webhook_is_ok: error_details.append(f"Webhook: {webhook_message}")
                acc.last_check_status_message = " | ".join(error_details)
            
            acc.last_check_timestamp = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # ส่งสถานะกลับไปว่าทำงานเสร็จแล้ว
        return jsonify({"status": "completed"})

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

