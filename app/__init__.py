import logging
import json

from flask import Flask, current_app
from .extensions import db, socketio
from pathlib import Path
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import jinja2.filters
import markupsafe
from datetime import datetime
from zoneinfo import ZoneInfo

login_manager = LoginManager() 

def create_app():
    root_path = Path(__file__).parent.parent

    app = Flask(__name__,
                template_folder=str(root_path / "templates"),
                static_folder=str(root_path / "static"))
                
    app.config.from_object('config.Config')
    # Apply logging level from config
    try:
        logging.getLogger().setLevel(app.config.get('LOG_LEVEL', 'INFO'))
    except Exception:
        pass

    # Set file upload folder and allowed extensions
    app.config['UPLOAD_FOLDER'] = str(root_path / 'static' / 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    # Match Nginx client_max_body_size (20M) to avoid mismatched limits
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # max file size 20MB

    db.init_app(app)
    # Configure Socket.IO using app config
    sio_kwargs = {
        'async_mode': app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet'),
        'ping_timeout': app.config.get('SOCKETIO_PING_TIMEOUT', 60),
        'ping_interval': app.config.get('SOCKETIO_PING_INTERVAL', 25),
        'logger': app.config.get('SOCKETIO_LOGGER', False),
        'engineio_logger': app.config.get('SOCKETIO_ENGINEIO_LOGGER', False),
    }
    cors_allowed = app.config.get('SOCKETIO_CORS_ALLOWED_ORIGINS')
    if cors_allowed is not None:
        sio_kwargs['cors_allowed_origins'] = cors_allowed
    message_queue = app.config.get('SOCKETIO_MESSAGE_QUEUE')
    if message_queue:
        sio_kwargs['message_queue'] = message_queue
    socketio.init_app(app, **sio_kwargs)
    login_manager.init_app(app)
    csrf = CSRFProtect(app)
    login_manager.login_view = 'auth.login' 
    
    # Register nl2br filter
    def nl2br(value):
        result = jinja2.filters.do_forceescape(value)
        result = result.replace('\n', markupsafe.Markup('<br>'))
        return result
    
    app.jinja_env.filters['nl2br'] = nl2br

    # Datetime helpers: convert UTC naive datetimes to configured local timezone
    def to_local(dt: datetime, fmt: str | None = None):
        if not dt:
            return ''
        try:
            tzname = app.config.get('TIMEZONE', 'UTC')
            tz = ZoneInfo(tzname)
            # Assume naive datetimes are in UTC as per models default
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo('UTC'))
            local_dt = dt.astimezone(tz)
            return local_dt.strftime(fmt) if fmt else local_dt
        except Exception:
            # Fallback: return original formatted if fmt provided
            return dt.strftime(fmt) if fmt else dt

    def fmt_time12(dt: datetime):
        return to_local(dt, '%I:%M %p')

    def fmt_date_time12(dt: datetime):
        return to_local(dt, '%b %d, %I:%M %p')

    def fmt_day_month(dt: datetime):
        return to_local(dt, '%b')

    def fmt_weekday(dt: datetime):
        return to_local(dt, '%a')

    app.jinja_env.filters['to_local'] = to_local
    app.jinja_env.filters['time12'] = fmt_time12
    app.jinja_env.filters['dt12'] = fmt_date_time12
    app.jinja_env.filters['mon'] = fmt_day_month
    app.jinja_env.filters['wday'] = fmt_weekday
    
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .admin import admin_bp
    from .office import office_bp
    from .student import student_bp
    from .super_admin import super_admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(office_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(super_admin_bp)

    from .models import User, SystemSettings

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @app.context_processor
    def inject_user():
        # Import here to avoid holding a LocalProxy at module import time
        from flask_login import current_user
        return dict(current_user=current_user)
    
    @app.context_processor
    def inject_system_settings():
        """Inject system settings and campus information into all templates"""
        # Import here to avoid holding a LocalProxy at module import time
        from flask_login import current_user
        from flask import url_for, request, session

        current_campus = None
        current_campus_name = 'PiyuGuide'
        brand_title = None
        brand_logo_url = None
        brand_tagline = None
        favicon_url = None
        campus_logo_url = None
        campus_theme = {
            'key': 'blue',
            'colors': {
                'primary': '#1e40af',
                'secondary': '#3b82f6',
                'accent': '#60a5fa'
            }
        }

        # Resolve current campus based on user/session
        try:
            if current_user.is_authenticated:
                try:
                    # Student: use their assigned campus if available
                    if getattr(current_user, 'role', None) == 'student' and \
                       getattr(current_user, 'student', None) and \
                       getattr(current_user.student, 'campus', None):
                        campus = current_user.student.campus
                        if campus:
                            current_campus = campus
                            current_campus_name = campus.name
                        else:
                            current_campus_name = SystemSettings.get_current_campus_name()
                    # Office admin: derive from their office
                    elif getattr(current_user, 'role', None) == 'office_admin' and \
                         getattr(current_user, 'office_admin', None) and \
                         getattr(current_user.office_admin, 'office', None) and \
                         getattr(current_user.office_admin.office, 'campus', None):
                        campus = current_user.office_admin.office.campus
                        if campus:
                            current_campus = campus
                            current_campus_name = campus.name
                        else:
                            current_campus_name = SystemSettings.get_current_campus_name()
                    # Super admin: may have campus_id on the user record
                    elif hasattr(current_user, 'campus_id') and current_user.campus_id:
                        from .models import Campus
                        campus = Campus.query.get(current_user.campus_id)
                        if campus:
                            current_campus = campus
                            current_campus_name = campus.name
                        else:
                            current_campus_name = SystemSettings.get_current_campus_name()
                except Exception:
                    current_campus_name = SystemSettings.get_current_campus_name()
            else:
                campus_id = request.args.get('campus_id') or session.get('selected_campus_id')
                if campus_id:
                    from .models import Campus
                    campus = Campus.query.get(campus_id)
                    if campus:
                        current_campus = campus
                        current_campus_name = campus.name
                        session['selected_campus_id'] = campus_id
                    else:
                        current_campus_name = SystemSettings.get_current_campus_name()
                else:
                    current_campus_name = SystemSettings.get_current_campus_name()
        except Exception:
            current_campus_name = 'PiyuGuide'

        # System-wide branding defaults
        try:
            from .models import SystemSettings as _Sys
            brand_title = _Sys.get_brand_title(default='PiyuGuide')
            logo_path = _Sys.get_brand_logo_path(default='images/schoollogo.png')
            brand_tagline = _Sys.get_brand_tagline(default='Campus Inquiry Management System')
            favicon_path = _Sys.get_favicon_path(default='images/schoollogo.png')

            if isinstance(logo_path, str) and (logo_path.startswith(('http://', 'https://', '/'))):
                brand_logo_url = logo_path
            else:
                brand_logo_url = url_for('static', filename=logo_path)

            if isinstance(favicon_path, str) and (favicon_path.startswith(('http://', 'https://', '/'))):
                favicon_url = favicon_path
            else:
                favicon_url = url_for('static', filename=favicon_path)
        except Exception:
            brand_title = 'PiyuGuide'
            brand_logo_url = url_for('static', filename='images/schoollogo.png')
            brand_tagline = 'Campus Inquiry Management System'
            favicon_url = brand_logo_url

        # Campus-specific overrides (logo + theme colors)
        try:
            theme_presets = {
                'blue':    {'primary': '#1e40af', 'secondary': '#3b82f6', 'accent': '#60a5fa'},
                'emerald': {'primary': '#065f46', 'secondary': '#10b981', 'accent': '#34d399'},
                'violet':  {'primary': '#4c1d95', 'secondary': '#8b5cf6', 'accent': '#a78bfa'},
                'sunset':  {'primary': '#9a3412', 'secondary': '#f97316', 'accent': '#fdba74'},
                'teal':    {'primary': '#134e4a', 'secondary': '#14b8a6', 'accent': '#2dd4bf'},
                'indigo':  {'primary': '#3730a3', 'secondary': '#6366f1', 'accent': '#818cf8'},
            }

            if current_campus is not None:
                clp = getattr(current_campus, 'campus_logo_path', None)
                if clp:
                    if isinstance(clp, str) and clp.startswith(('http://', 'https://', '/')):
                        campus_logo_url = clp
                    else:
                        campus_logo_url = url_for('static', filename=clp)
                else:
                    campus_logo_url = brand_logo_url

                key = getattr(current_campus, 'campus_theme_key', None) or 'blue'
                if key not in theme_presets:
                    key = 'blue'
                campus_theme = { 'key': key, 'colors': theme_presets[key] }
            else:
                campus_logo_url = brand_logo_url
        except Exception:
            campus_logo_url = brand_logo_url

        return dict(
            current_campus_name=current_campus_name,
            current_campus=current_campus,
            brand_title=brand_title,
            brand_logo_url=brand_logo_url,
            brand_tagline=brand_tagline,
            favicon_url=favicon_url,
            campus_logo_url=campus_logo_url,
            campus_theme=campus_theme
        )

    @app.context_processor
    def inject_webrtc_ice():
        """Expose ICE servers to templates for WebRTC clients.
        Priority:
          1. ICE_SERVERS_JSON (full explicit list as JSON string)
          2. TURN_HOST (+ TURN_USERNAME + TURN_PASSWORD) -> expand into STUN + TURN (udp,tcp,tls)
          3. TURN_URL (+ TURN_USERNAME + TURN_PASSWORD) legacy single entry
          4. None (client JS will fallback to public STUN list ONLY - NOT suitable for multi-ISP / carrier NAT)
        """
        ice_servers = None
        cfg = app.config
        try:
            if cfg.get('ICE_SERVERS_JSON'):
                try:
                    ice_servers = json.loads(cfg['ICE_SERVERS_JSON'])
                except Exception:
                    ice_servers = None
            elif cfg.get('TURN_HOST') and cfg.get('TURN_USERNAME') and cfg.get('TURN_PASSWORD'):
                host = cfg['TURN_HOST'].replace('turn:', '').replace('stun:', '')
                uname = cfg['TURN_USERNAME']
                cred = cfg['TURN_PASSWORD']
                # Build a comprehensive list covering UDP, TCP and TLS
                ice_servers = [
                    { 'urls': [f'stun:{host}:3478'] },
                    {
                        'urls': [
                            f'turn:{host}:3478?transport=udp',
                            f'turn:{host}:3478?transport=tcp',
                            # TLS on standard TURN-TLS port
                            f'turns:{host}:5349?transport=tcp',
                            # Extra TLS fallback on 443 for restrictive firewalls
                            f'turns:{host}:443?transport=tcp'
                        ],
                        'username': uname,
                        'credential': cred
                    }
                ]
            elif cfg.get('TURN_URL') and cfg.get('TURN_USERNAME') and cfg.get('TURN_PASSWORD'):
                # Legacy single TURN_URL support
                ice_servers = [{
                    'urls': cfg['TURN_URL'],
                    'username': cfg['TURN_USERNAME'],
                    'credential': cfg['TURN_PASSWORD']
                }]
        except Exception:
            ice_servers = None
        return dict(ICE_SERVERS=ice_servers)

    @app.context_processor
    def inject_notifications_for_super_admin():
        """Inject unread count and sidebar notifications for Super Super Admin layout."""
        try:
            from app.models import Notification
            if login_manager._login_disabled:
                return {}
            from flask_login import current_user as _cu
            if getattr(_cu, 'is_authenticated', False) and getattr(_cu, 'role', '') == 'super_super_admin':
                from sqlalchemy import desc
                unread = Notification.query.filter_by(user_id=_cu.id, is_read=False).count()
                items = Notification.query.filter_by(user_id=_cu.id).order_by(desc(Notification.created_at)).limit(10).all()
                return dict(unread_notifications_count=unread, sidebar_notifications=items)
        except Exception:
            pass
        return {}

    @app.context_processor
    def inject_profile_img_helper():
        def profile_img_url(user, size: int | None = None):
            """Return cache-busted static URL for a user's profile picture.

            Uses stored user.profile_pic (original derivative) and optional size (128/256/512) pattern
            produced by save_profile_image. Falls back to original if sized variant assumed missing.
            Returns None if user has no picture.
            """
            try:
                if not user or not getattr(user, 'profile_pic', None):
                    return None
                base_path = user.get_profile_pic_path() if hasattr(user, 'get_profile_pic_path') else user.profile_pic
                if not base_path:
                    return None
                sized_path = base_path
                if size and str(size).isdigit():
                    import os
                    root, ext = os.path.splitext(base_path)
                    sized_path = f"{root}_{size}{ext}"  # optimistic
                from flask import url_for
                return url_for('static', filename=sized_path) + f"?v={user.profile_pic}"
            except Exception:
                return None
        return dict(profile_img_url=profile_img_url)

    @app.context_processor
    def inject_asset_version():
        """Inject a global ASSET_VERSION used for cache-busting static assets.

        Priority:
          1. Use ASSET_VERSION from environment/app config if provided (e.g., release/build number)
          2. Fallback to app startup epoch seconds to ensure a fresh version per deploy
        """
        try:
            ver = app.config.get('ASSET_VERSION')
            if not ver:
                import time
                ver = str(int(time.time()))
                # Store to keep it stable for the lifetime of the app
                app.config['ASSET_VERSION'] = ver
        except Exception:
            ver = '1'
        return dict(ASSET_VERSION=ver)
    
    with app.app_context():
        # Initialize websocket handlers
        from app.websockets import init_websockets
        init_websockets()
        
        # Initialize the video session scheduler
        from app.office.routes.office_counseling import init_scheduler
        init_scheduler(app)
        
    return app