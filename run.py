import eventlet
eventlet.monkey_patch()
print("1 monkey patched", flush=True)

# imports ที่ต้องเกิดหลัง monkey_patch เท่านั้น
print("2 before imports", flush=True)
from app import create_app
print("3 after import create_app", flush=True)
app = create_app()
print("4 app created", flush=True)

# import socketio จาก extension ที่สร้างไว้ในแอป
from app.extensions import socketio
print("5 imported socketio", flush=True)

if __name__ == "__main__":
    print("6 about to run socketio", flush=True)
    # production จะรันด้วย gunicorn แต่ไฟล์นี้ช่วยรันทดสอบด้วย python run.py ได้
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    print("7 socketio returned (unexpected)", flush=True)
