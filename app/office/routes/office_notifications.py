from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Notification, db
from app.utils import role_required
from app.office import office_bp
from datetime import datetime


@office_bp.route('/notifications')
@login_required
@role_required(['office_admin'])
def office_notifications():
    """Display notifications page for office admins"""
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Number of notifications per page
    
    # Get all notifications for the current user
    notifications_query = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc())
    
    # Filter by read status if specified
    read_filter = request.args.get('read')
    if read_filter == 'unread':
        notifications_query = notifications_query.filter_by(is_read=False)
    elif read_filter == 'read':
        notifications_query = notifications_query.filter_by(is_read=True)
    
    # Filter by type if specified
    type_filter = request.args.get('type')
    if type_filter:
        notifications_query = notifications_query.filter_by(notification_type=type_filter)
    
    # Paginate results
    notifications_paginated = notifications_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get notification statistics
    total_notifications = Notification.query.filter_by(user_id=current_user.id).count()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    read_count = total_notifications - unread_count
    
    # Get notification type counts
    type_counts = db.session.query(
        Notification.notification_type,
        db.func.count(Notification.id).label('count')
    ).filter_by(user_id=current_user.id).group_by(Notification.notification_type).all()
    
    type_stats = {type_name: count for type_name, count in type_counts}
    
    return render_template('office/office_notifications.html',
                         notifications=notifications_paginated.items,
                         pagination=notifications_paginated,
                         total_notifications=total_notifications,
                         unread_count=unread_count,
                         read_count=read_count,
                         type_stats=type_stats,
                         current_filter_read=read_filter,
                         current_filter_type=type_filter)


@office_bp.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
@role_required(['office_admin'])
def mark_notification_read(notification_id):
    """Mark a specific notification as read"""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Notification marked as read'})


@office_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@role_required(['office_admin'])
def mark_all_notifications_read():
    """Mark all notifications as read for the current user"""
    unread_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).all()
    
    count = len(unread_notifications)
    
    for notification in unread_notifications:
        notification.is_read = True
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'{count} notifications marked as read'})


@office_bp.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
@login_required
@role_required(['office_admin'])
def delete_notification(notification_id):
    """Delete a specific notification"""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Notification deleted'})


@office_bp.route('/notifications/delete-all-read', methods=['DELETE'])
@login_required
@role_required(['office_admin'])
def delete_all_read_notifications():
    """Delete all read notifications for the current user"""
    read_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).all()
    
    count = len(read_notifications)
    
    for notification in read_notifications:
        db.session.delete(notification)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'{count} read notifications deleted'})


@office_bp.route('/notifications/get-unread-count')
@login_required
@role_required(['office_admin'])
def get_unread_count():
    """Get the count of unread notifications for live updates"""
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'unread_count': unread_count})
