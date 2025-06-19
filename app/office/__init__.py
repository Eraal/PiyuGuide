from flask import Blueprint

office_bp = Blueprint('office', __name__, url_prefix='/office')

from .routes import office_base, office_dashboard, office_acount_settings, office_inquiries, office_counseling, office_announcements
from .routes import office_activity_logs, office_team