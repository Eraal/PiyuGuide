from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60, ping_interval=25, logger=True, engineio_logger=True)