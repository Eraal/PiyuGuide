from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate

db = SQLAlchemy()
# SocketIO will be configured in app factory based on app.config
socketio = SocketIO()
"""Database migration handler (initialized in app factory)."""
migrate = Migrate()