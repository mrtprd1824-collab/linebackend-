# run.py
import eventlet
eventlet.monkey_patch()

import os

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False)
