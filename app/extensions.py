from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate
try:
	from flask_mail import Mail
except Exception:  # pragma: no cover
	class Mail:  # type: ignore
		def init_app(self, app):
			pass

db = SQLAlchemy()
# SocketIO will be configured in app factory based on app.config
socketio = SocketIO()
"""Database migration handler (initialized in app factory)."""
migrate = Migrate()
"""Mail extension for SMTP email sending (initialized in app factory)."""
mail = Mail()