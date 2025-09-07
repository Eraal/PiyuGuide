from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

db = SQLAlchemy()
# SocketIO will be configured in app factory based on app.config
socketio = SocketIO()