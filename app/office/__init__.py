from flask import Blueprint
from flask_login import current_user
from app.models import Notification

office_bp = Blueprint('office', __name__, url_prefix='/office')

# Context processor to inject unread notifications count for office templates
@office_bp.context_processor
def inject_office_notifications():
    """Inject unread notifications count and recent notifications for office admin users"""
    if current_user.is_authenticated and hasattr(current_user, 'office_admin') and current_user.office_admin:
        # Base notification data always available
        unread_notifications_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        recent_notifications = Notification.query.filter_by(
            user_id=current_user.id
        ).order_by(Notification.created_at.desc()).limit(5).all()

    # Defaults for sidebar badges and counseling flags
        pending_inquiries_count = 0
        upcoming_sessions_count = 0
        office_offers_counseling = False
        office_supports_video = False

        try:
            # Lazy imports here to avoid circular imports at module load
            from datetime import datetime
            from app.models import Inquiry, CounselingSession, OfficeConcernType, Office

            office_id = current_user.office_admin.office_id
            now = datetime.utcnow()

            # Sidebar counts
            pending_inquiries_count = Inquiry.query.filter_by(
                office_id=office_id,
                status='pending'
            ).count()

            upcoming_sessions_count = CounselingSession.query.filter(
                CounselingSession.office_id == office_id,
                CounselingSession.status.in_(['pending', 'confirmed']),
                CounselingSession.scheduled_at > now
            ).count()

            # Counseling availability flag (strictly controlled by Campus Admin toggle)
            # When disabled (supports_video == False), hide all counseling UI in Office module
            office_obj = Office.query.get(office_id)
            office_supports_video = bool(getattr(office_obj, 'supports_video', False)) if office_obj else False
            office_offers_counseling = office_supports_video
        except Exception:
            # Fail-safe: keep defaults if any query fails
            pass

        # NOTE: pending_inquiries_count purposely reflects ONLY inquiries with status 'pending'.
        # If in future we introduce a separate "new" flag distinct from status, adapt this query
        # here so the sidebar badge always represents actionable (unhandled) inquiries.
        return {
            'unread_notifications_count': unread_notifications_count,
            'sidebar_unread_notifications_count': unread_notifications_count,
            'sidebar_notifications': recent_notifications,
            'pending_inquiries_count': pending_inquiries_count,
            'upcoming_sessions_count': upcoming_sessions_count,
            'office_offers_counseling': office_offers_counseling,
            'office_supports_video': office_supports_video,
        }
    return {
        'unread_notifications_count': 0,
        'sidebar_unread_notifications_count': 0,
        'sidebar_notifications': [],
        'pending_inquiries_count': 0,
        'upcoming_sessions_count': 0,
        'office_offers_counseling': False,
        'office_supports_video': False,
    }

from .routes import office_base, office_dashboard, office_acount_settings, office_inquiries, office_counseling, office_announcements, office_notifications
from .routes import office_activity_logs, office_team, office_reports, office_concern_types, office_counseling_concern_types