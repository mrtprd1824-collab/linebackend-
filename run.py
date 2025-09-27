# run.py
import eventlet
eventlet.monkey_patch()

import os
import click
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import socketio, db
from app.models import User

app = create_app()

# ---- โค้ดสำหรับสร้างแอดมิน ----
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
        # --- แก้ไขตรงนี้ ---
        password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        # --- จบส่วนที่แก้ไข ---
        is_admin=True
    )

    db.session.add(new_admin)
    db.session.commit()

    print(f"สร้างแอดมิน '{email}' เรียบร้อยแล้ว")
# ---- จบส่วนโค้ดสร้างแอดมิน ----


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False)

