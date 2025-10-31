import os
import json


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


def _parse_cors_list(value: str | None):
    if not value:
        return None  # None = same-origin only for Socket.IO
    items = [v.strip() for v in value.split(',') if v.strip()]
    return items or None


class Config:
    # Core app
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
    TIMEZONE = os.getenv('APP_TIMEZONE', 'Asia/Manila')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://postgres:admin@localhost/piyuTesting')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cookies / Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _get_bool('SESSION_COOKIE_SECURE', False)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'https' if SESSION_COOKIE_SECURE else 'http')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Flask-SocketIO
    SOCKETIO_ASYNC_MODE = os.getenv('SOCKETIO_ASYNC_MODE', 'eventlet')
    SOCKETIO_PING_TIMEOUT = _get_int('SOCKETIO_PING_TIMEOUT', 60)
    SOCKETIO_PING_INTERVAL = _get_int('SOCKETIO_PING_INTERVAL', 25)
    SOCKETIO_CORS_ALLOWED_ORIGINS = _parse_cors_list(os.getenv('SOCKETIO_CORS_ALLOWED_ORIGINS'))
    SOCKETIO_LOGGER = _get_bool('SOCKETIO_LOGGER', False)
    SOCKETIO_ENGINEIO_LOGGER = _get_bool('SOCKETIO_ENGINEIO_LOGGER', False)
    SOCKETIO_MESSAGE_QUEUE = os.getenv('SOCKETIO_MESSAGE_QUEUE')  # e.g., redis://localhost:6379/0

    # WebRTC ICE/TURN configuration
    # Provide either ICE_SERVERS_JSON (full JSON list) or TURN_* to add a single TURN server.
    ICE_SERVERS_JSON = os.getenv('ICE_SERVERS_JSON')
    # Preferred: provide TURN_HOST so app can auto-expand UDP/TCP/TLS variants
    TURN_HOST = os.getenv('TURN_HOST')  # e.g., turn.example.com
    TURN_URL = os.getenv('TURN_URL')  # e.g., turn:turn.example.com:3478?transport=udp
    TURN_USERNAME = os.getenv('TURN_USERNAME')
    TURN_PASSWORD = os.getenv('TURN_PASSWORD')

    # Email (SMTP) - defaults tuned for Brevo (Sendinblue)
    # NOTE: Do NOT hardcode credentials here. Provide them via environment variables.
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp-relay.brevo.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = _get_bool('MAIL_USE_TLS', True)
    MAIL_USE_SSL = _get_bool('MAIL_USE_SSL', False)
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')  # Brevo SMTP login (set via environment)
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')  # Brevo SMTP key (set via environment)
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'PiyuGuide <no-reply@piyuguide.live>')
    # When True, Flask-Mail does NOT actually send emails (used for tests). Ensure this is False in real tests.
    MAIL_SUPPRESS_SEND = _get_bool('MAIL_SUPPRESS_SEND', False)
    # Optional HTTP API fallback (Brevo v3)
    BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')
    BREVO_API_URL = os.getenv('BREVO_API_URL', 'https://api.brevo.com/v3/smtp/email')
