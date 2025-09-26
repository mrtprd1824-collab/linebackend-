from flask import Blueprint, render_template, request, redirect, url_for, flash , session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, db
from app.models import OAGroup
from flask import session, redirect, url_for

bp = Blueprint("auth", __name__)

# ============ login ===================

@bp.route("/login", methods=["GET", "POST"])
def login():
    print(">>> login() called, method:", request.method)  # debug

    if current_user.is_authenticated: # ถ้า login แล้ว
        return redirect(url_for("auth.dashboard")) # ให้ไปที่หน้า dashboard

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("auth.dashboard"))
        else:
            flash("Invalid email or password", "danger")
            # แก้ไขจุดที่ 1: เพิ่ม redirect หลังจาก flash
            return redirect(url_for("auth.login"))
        
    session.permanent = True
            
    # แก้ไขจุดที่ 2: ระบุ path ของ template ให้ถูกต้อง
    return render_template("login.html")

# =============== dashboard =================

@bp.route("/dashboard")
@login_required
def dashboard():
    groups = OAGroup.query.order_by(OAGroup.name).all()
    return render_template("dashboard.html", groups=groups)


# =============== logout =================

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# ================= profile ==============

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # เราจะใช้ current_user ที่ได้จาก Flask-Login โดยตรง
    user = current_user

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # 1. ตรวจสอบว่ารหัสผ่านที่กรอก 2 ครั้งตรงกันหรือไม่
        if new_password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('auth.profile'))

        # 2. ตรวจสอบความยาวของรหัสผ่าน
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return redirect(url_for('auth.profile'))
            
        # 3. ถ้าทุกอย่างถูกต้อง, ตั้งรหัสผ่านใหม่และบันทึก
        user.set_password(new_password)
        db.session.commit()
        
        flash('Your password has been updated successfully!', 'success')
        return redirect(url_for('auth.profile'))

    # ถ้าเป็น GET request, ให้แสดงหน้า profile.html ปกติ
    return render_template('profile.html', user=user)

#============== เลือกกลุ่มหน้าแรก ================

@bp.route("/select-groups", methods=['POST']) # เปลี่ยนเป็น select-groups และรับ POST
@login_required
def select_groups():
    # รับค่า group_ids ที่เป็น list จากฟอร์ม
    group_ids = request.form.getlist('group_ids', type=int)
    # บันทึก list ลงใน session
    session['active_group_ids'] = group_ids # เปลี่ยนชื่อ session key ด้วย
    return redirect(url_for('chats.index'))

@bp.route("/clear-group-filter")
@login_required
def clear_group_filter():
    # ลบ session key ที่ถูกต้อง
    session.pop('active_group_ids', None)
    return redirect(url_for('chats.index'))
