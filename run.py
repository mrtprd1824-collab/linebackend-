import os
import click
from werkzeug.security import generate_password_hash

# ★★★ แก้ไขการ import ตรงนี้ ★★★
# เราจะ import แค่ create_app จาก app และ import ส่วนอื่นๆ จาก extensions
from app import create_app
from app.extensions import db, socketio
# ★★★ จบส่วนแก้ไขการ import ★★★

from app.models import User

app = create_app()

@app.cli.command("create-admin")
@click.argument("email")
@click.argument("password")
def create_admin(email, password):
    """สร้างผู้ใช้งานแอดมินคนแรก"""
    if User.query.filter_by(email=email).first():
        print(f"Error: อีเมล '{email}' มีอยู่ในระบบแล้ว")
        return

    new_admin = User(
        email=email,
        password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        is_admin=True
    )

    db.session.add(new_admin)
    db.session.commit()

    print(f"สร้างแอดมิน '{email}' เรียบร้อยแล้ว")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # ใช้ use_reloader=False เพื่อให้ทำงานกับ eventlet ได้อย่างเสถียร
    socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False)