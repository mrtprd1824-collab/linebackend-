import eventlet
eventlet.monkey_patch()  # ต้องมาก่อน import อื่น

from app import create_app
from app.extensions import socketio

app = create_app()  # gunicorn จะโหลด 'app'
