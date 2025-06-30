from flask import Blueprint
from flask_login import current_user
from app.models import Notification

office_bp = Blueprint('office', __name__, url_prefix='/office')

# Context processor to inject unread notifications count for office templates
@office_bp.context_processor
def inject_office_notifications():
    """Inject unread notifications count and recent notifications for office admin users"""
    if current_user.is_authenticated and hasattr(current_user, 'office_admin') and current_user.office_admin:
        unread_notifications_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
        
        # Get recent notifications for sidebar (limit to 5)
        recent_notifications = Notification.query.filter_by(
            user_id=current_user.id
        ).order_by(Notification.created_at.desc()).limit(5).all()
        
        return {
            'unread_notifications_count': unread_notifications_count,
            'sidebar_notifications': recent_notifications
        }
    return {
        'unread_notifications_count': 0,
        'sidebar_notifications': []
    }

from .routes import office_base, office_dashboard, office_acount_settings, office_inquiries, office_counseling, office_announcements, office_notifications
from .routes import office_activity_logs, office_team, office_reports