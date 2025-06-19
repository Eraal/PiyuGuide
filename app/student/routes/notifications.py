from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Notification, db
from app.utils import student_required

# Use a blueprint from the parent package if it exists
from app.student import student_bp

@student_bp.route('/notifications')
@login_required
@student_required
def notifications():
    """Route to display all student notifications"""
    # Get all notifications for the current student, sorted by creation time (newest first)
    notifications = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc())\
        .all()
    
    # Get count of unread notifications
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).count()
    
    return render_template(
        'student/notifications.html',
        notifications=notifications,
        unread_notifications_count=unread_notifications_count
    )

# API endpoint for marking a notification as read/dismissed
@student_bp.route('/api/notifications/<int:notification_id>/dismiss', methods=['POST'])
@login_required
@student_required
def dismiss_notification(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    
    # Security check: ensure the notification belongs to the current user
    if notification.user_id != current_user.id:
        return jsonify(success=False, message="Unauthorized"), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify(success=True)

# API endpoint for marking all notifications as read
@student_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
@student_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({
        'is_read': True
    })
    db.session.commit()
    
    return jsonify(success=True)