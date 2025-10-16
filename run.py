# run.py (สำหรับรัน local)
if __name__ == "__main__":
    import eventlet
    eventlet.monkey_patch()
    from app import create_app
    from app.extensions import socketio
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)

else:
    # ให้ gunicorn ใช้ wsgi_eventlet.py แทน ไม่ต้องมีอะไรที่นี่
    from app import create_app
    app = create_app()
