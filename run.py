import eventlet
eventlet.monkey_patch()
print("1 monkey patched", flush=True)

# หลังจากนี้บรรทัด import อื่น ๆ
print("2 before imports", flush=True)
from app import create_app
print("3 after import create_app", flush=True)
print("4 calling create_app", flush=True)
app = create_app()
print("5 app created", flush=True)

# ถ้ามี socketio import
from app.extensions import socketio
print("6 imported socketio", flush=True)

if __name__ == '__main__':
    print("7 about to run socketio", flush=True)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    print("8 socketio returned (should not reach)", flush=True)