import eventlet
eventlet.monkey_patch(thread=False)
# ★★★ จบส่วนที่เพิ่ม ★★★

import os
import click
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db, socketio
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
    # ★★★ เพิ่ม use_reloader=False เข้าไปเพื่อปิดการใช้งาน reloader ที่ขัดแย้งกับ eventlet ★★★
    socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False)