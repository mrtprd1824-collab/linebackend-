# run.py
import os

# ✅ monkey_patch เฉพาะตอนรันตรง ๆ เท่านั้น
if __name__ == "__main__":
    import eventlet
    eventlet.monkey_patch()
    print("eventlet monkey-patched (local run)", flush=True)

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # local dev only
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
