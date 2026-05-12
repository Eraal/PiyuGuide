from flask import Blueprint
from flask_login import current_user
from app.models import Notification, User, Office, Announcement

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.context_processor
def inject_campus_admin_notifications():
	"""Inject unread announcement notifications for campus admin (super_admin) users.

	We scope notifications to type 'campus_announcement' so they don't collide with
	generic office notifications. Falls back to empty list for other roles.
	"""
	if current_user.is_authenticated and getattr(current_user, 'role', None) == 'super_admin':
		unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False, notification_type='campus_announcement').count()
		recent = Notification.query.filter_by(user_id=current_user.id, notification_type='campus_announcement').order_by(Notification.created_at.desc()).limit(8).all()
		return {
			'campus_unread_notifications_count': unread_count,
			'campus_sidebar_notifications': recent
		}
	return {
		'campus_unread_notifications_count': 0,
		'campus_sidebar_notifications': []
	}

from .routes import dashboard, adminprofile, student_management, audit_logs
from .routes import office_stats, admin_announcement, admin_inquiries
from .routes import account_settings, add_office, manage_office_admins, edit_office
from .routes import locked_account_history, admin_detail, manage_concern_types
from .routes import edit_admin, admin_counseling, manage_admin
from .routes import system_customization
from .routes import manage_departments
