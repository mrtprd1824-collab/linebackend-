from flask import Blueprint, render_template, redirect, url_for, request, flash , jsonify 
from flask_login import login_required, current_user
from app.models import User
from app.extensions import db
from datetime import timedelta
from app.models import LineAccount
from app.services.oa_checker import check_single_oa_status

bp = Blueprint("admin", __name__, url_prefix="/admin")

# decorator สำหรับเช็คสิทธิ์ admin
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if current_user.is_authenticated:
            print(f"--- DEBUG: Checking role for user '{current_user.email}'. Actual role is: '{current_user.role}' ---")

        if not current_user.is_authenticated or current_user.role != "admin":
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("auth.login"))
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
@login_required # หรือ @admin_required ถ้ามี
def oa_health_check_page():
    all_accounts = LineAccount.query.order_by(
        LineAccount.is_active.asc(),
        LineAccount.name.asc()
    ).all()
    return render_template('admin/oa_health_check.html',
                           accounts=all_accounts,
                           timedelta=timedelta)

@bp.route('/api/run-oa-check', methods=['POST'])
@login_required # หรือ @admin_required ถ้ามี
def run_oa_check_api():
    all_accounts = LineAccount.query.all()
    results = {}
    for acc in all_accounts:
        status = check_single_oa_status(acc)
        results[acc.id] = 'OK' if status else acc.last_check_status_message
    
    db.session.commit() # Commit การเปลี่ยนแปลงทั้งหมดทีเดียวหลัง Loop เสร็จ
    
    return jsonify({"status": "completed", "results": results})