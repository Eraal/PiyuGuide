from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc
from app.models import Notification, db
from app.utils import student_required

# Use a blueprint from the parent package if it exists
from app.student import student_bp


@student_bp.route('/notifications')
@login_required
@student_required
def notifications():
    """Display notifications page for students with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Base query
    notifications_query = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc())

    # Filters
    read_filter = request.args.get('read')
    if read_filter == 'unread':
        notifications_query = notifications_query.filter_by(is_read=False)
    elif read_filter == 'read':
        notifications_query = notifications_query.filter_by(is_read=True)

    type_filter = request.args.get('type')
    if type_filter:
        notifications_query = notifications_query.filter_by(notification_type=type_filter)

    # Paginate
    notifications_paginated = notifications_query.paginate(page=page, per_page=per_page, error_out=False)

    # Stats
    total_notifications = Notification.query.filter_by(user_id=current_user.id).count()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    read_count = total_notifications - unread_count

    # Notifications for navbar dropdown (recent few)
    notifications_nav = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()

    # Top navbar needs counts for badge; also provide a small recent list if desired elsewhere
    return render_template(
        'student/notifications.html',
    page_notifications=notifications_paginated.items,
        pagination=notifications_paginated,
        total_notifications=total_notifications,
        unread_count=unread_count,
        read_count=read_count,
        unread_notifications_count=unread_count,
    notifications=notifications_nav,
        current_filter_read=read_filter,
        current_filter_type=type_filter
    )


# Student notifications actions (mirroring Office module)
@student_bp.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
@student_required
def mark_notification_read(notification_id):
    """Mark a specific notification as read"""
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Notification marked as read'})


@student_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@student_required
def mark_all_notifications_read():
    """Mark all notifications as read for current student"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True, 'message': f'{count} notifications marked as read'})


@student_bp.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
@login_required
@student_required
def delete_notification(notification_id):
    """Delete a specific notification"""
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Notification deleted'})


@student_bp.route('/notifications/delete-all-read', methods=['DELETE'])
@login_required
@student_required
def delete_all_read_notifications():
    """Delete all read notifications"""
    read_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=True).all()
    count = len(read_notifications)
    for n in read_notifications:
        db.session.delete(n)
    db.session.commit()
    return jsonify({'success': True, 'message': f'{count} read notifications deleted'})


@student_bp.route('/notifications/get-unread-count')
@login_required
@student_required
def get_unread_count():
    """Return unread notifications count for the student"""
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'unread_count': unread_count})


# Backward compatible API endpoints used in existing UI (delegate to new handlers)
@student_bp.route('/api/notifications/<int:notification_id>/dismiss', methods=['POST'])
@login_required
@student_required
def dismiss_notification(notification_id):
    """Previously used endpoint to mark single notification read"""
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify(success=True)


@student_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
@student_required
def mark_all_read():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify(success=True, message=f'{count} notifications marked as read')