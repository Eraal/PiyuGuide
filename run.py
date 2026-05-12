import os
import eventlet
# Apply Eventlet monkey patching before any other imports
eventlet.monkey_patch()

from pathlib import Path
from app import create_app, socketio

# Ensure project root on sys.path
import sys
sys.path.append(str(Path(__file__).parent))

app = create_app()

if __name__ == "__main__":
    # Local development server only. For production, use Gunicorn with eventlet:
    # gunicorn -k eventlet -w 1 -b 127.0.0.1:8000 "app:create_app()"
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', '1').lower() in ('1', 'true', 'yes', 'on')
    socketio.run(app, debug=debug, host=host, port=port, use_reloader=debug)