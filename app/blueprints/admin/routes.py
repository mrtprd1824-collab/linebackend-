from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import User
from app.extensions import db

bp = Blueprint("admin", __name__, url_prefix="/admin")

# decorator สำหรับเช็คสิทธิ์ admin
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
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