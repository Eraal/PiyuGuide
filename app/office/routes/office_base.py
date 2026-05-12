from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import Inquiry, CounselingSession, Student, User, OfficeAdmin, Announcement, Notification
from app.utils import role_required
from .office_dashboard import get_dashboard_stats, get_chart_data, get_most_frequent_concerns
from app.office import office_bp
from app.extensions import db


@office_bp.route('/dashboard')
@login_required
@role_required(['office_admin'])
def dashboard():
    """Render the office dashboard view"""
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    now = datetime.utcnow()
    
    # Get dashboard statistics
    stats = get_dashboard_stats(office_id)
    chart_data = get_chart_data(office_id)
    
    # Get most frequent concerns for the office
    most_frequent_concerns = get_most_frequent_concerns(office_id, days=30)
    
    # Get recent inquiries
    recent_inquiries = Inquiry.query.filter_by(office_id=office_id).order_by(
        Inquiry.created_at.desc()
    ).limit(5).all()
    
    # Get today's sessions
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    
    todays_sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= today_start,
        CounselingSession.scheduled_at <= today_end
    ).order_by(CounselingSession.scheduled_at).all()
    
    # Get online staff
    online_staff = User.query.join(OfficeAdmin).filter(
        OfficeAdmin.office_id == office_id,
        User.is_online == True,
        User.last_activity > now - timedelta(minutes=15)  # Consider online if active in last 15 min
    ).all()
    
    # Get recent announcements
    recent_announcements = Announcement.query.filter(
        (Announcement.target_office_id == office_id) | (Announcement.is_public == True)
    ).order_by(Announcement.created_at.desc()).limit(3).all()
    
    # Add counts needed by the base template
    # Count of pending inquiries for the badge in sidebar
    pending_inquiries_count = Inquiry.query.filter_by(
        office_id=office_id, 
        status='pending'
    ).count()
    
    # Count of upcoming counseling sessions for the badge in sidebar
    upcoming_sessions_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= now,
        CounselingSession.status.in_(['scheduled', 'confirmed'])
    ).count()
    
    # Count of unread notifications
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).count()
    
    # Get recent notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('office/office_dashboard.html', 
                          stats=stats,
                          chart_data=chart_data,
                          most_frequent_concerns=most_frequent_concerns,
                          recent_inquiries=recent_inquiries,
                          todays_sessions=todays_sessions,
                          online_staff=online_staff,
                          recent_announcements=recent_announcements,
                          pending_inquiries_count=pending_inquiries_count,
                          upcoming_sessions_count=upcoming_sessions_count,
                          unread_notifications_count=unread_notifications_count,
                          notifications=notifications,
                          now=now)


@office_bp.route('/dashboard_data')
@login_required
@role_required(['office_admin'])
def dashboard_data():
    """API endpoint to get updated dashboard data for AJAX refreshes"""
    if not hasattr(current_user, 'office_admin'):
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Get updated statistics
    stats = get_dashboard_stats(office_id)
    chart_data = get_chart_data(office_id)
    most_frequent_concerns = get_most_frequent_concerns(office_id, days=30)
    
    # Get counts for badges
    now = datetime.utcnow()
    pending_inquiries_count = Inquiry.query.filter_by(
        office_id=office_id, 
        status='pending'
    ).count()
    
    upcoming_sessions_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= now,
        CounselingSession.status.in_(['scheduled', 'confirmed'])
    ).count()
    
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).count()
    
    return jsonify({
        'stats': stats,
        'chart_data': chart_data,
        'most_frequent_concerns': most_frequent_concerns,
        'pending_inquiries_count': pending_inquiries_count,
        'upcoming_sessions_count': upcoming_sessions_count,
        'unread_notifications_count': unread_notifications_count,
        'last_updated': datetime.utcnow().strftime('%B %d, %Y %H:%M')
    })
    
    stats = get_dashboard_stats(office_id)
    chart_data = get_chart_data(office_id)
    
    return jsonify({
        'stats': stats,
        'chart_data': chart_data
    })


@office_bp.route('/api/heartbeat', methods=['POST'])
@login_required
def office_heartbeat():
    """Lightweight heartbeat to keep office staff presence fresh.

    Updates the current user's last_activity and ensures is_online remains True
    while their session is valid. Intended to be called periodically from
    office pages.
    """
    # Only allow office admins to use this heartbeat
    if not hasattr(current_user, 'role') or current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403

    try:
        current_user.last_activity = datetime.utcnow()
        # Keep the user marked online during active session/heartbeat
        if current_user.is_online is not True:
            current_user.is_online = True
        db.session.commit()
        return jsonify({
            'ok': True,
            'server_time': datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'heartbeat_failed', 'detail': str(e)}), 500