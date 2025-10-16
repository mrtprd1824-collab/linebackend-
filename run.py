import os

_EVENTLET_PATCHED = False


def _monkey_patch_if_needed():
    """Apply eventlet monkey patching only when explicitly enabled."""
    global _EVENTLET_PATCHED
    if _EVENTLET_PATCHED:
        return True
    if os.environ.get("ENABLE_EVENTLET_PATCH", "1") == "1":
        import eventlet  # imported lazily so disabling stays cheap
        eventlet.monkey_patch(os=False)
        print("1 monkey patched (os=False)", flush=True)
        _EVENTLET_PATCHED = True
        return True
    print("1 eventlet monkey patch disabled by env", flush=True)
    return False


_monkey_patch_if_needed()

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
