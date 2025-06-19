from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import desc
from app.student import student_bp
from app.models import (
    Inquiry, CounselingSession, Student, User, 
    Office, Announcement, StudentActivityLog, Notification
)
from app.extensions import db
from app.utils import role_required

@student_bp.route('/dashboard')
@login_required
@role_required(['student'])
def dashboard():
    """Render the student dashboard with relevant statistics and recent activities"""
    # Get the current date for welcome message
    today = datetime.utcnow()
    
    # Get the student record for the current user
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Calculate statistics
    stats = {
        'pending_inquiries': Inquiry.query.filter_by(student_id=student.id, status='pending').count(),
        'total_inquiries': Inquiry.query.filter_by(student_id=student.id).count(),
        'upcoming_sessions': CounselingSession.query.filter(
            CounselingSession.student_id == student.id, 
            CounselingSession.scheduled_at > today,
            CounselingSession.status.in_(['pending', 'confirmed'])
        ).count(),
        'new_announcements': Announcement.query.filter(
            Announcement.created_at >= (today - timedelta(days=7))
        ).count()
    }
    
    # Get upcoming schedule (next 7 days)
    upcoming_schedule = CounselingSession.query.filter(
        CounselingSession.student_id == student.id,
        CounselingSession.scheduled_at >= today,
        CounselingSession.scheduled_at <= today + timedelta(days=7),
        CounselingSession.status.in_(['pending', 'confirmed'])
    ).order_by(CounselingSession.scheduled_at).all()
    
    # Mark sessions scheduled for today
    for session in upcoming_schedule:
        session.is_today = session.scheduled_at.date() == today.date()
    
    # Get recent inquiries
    recent_inquiries = Inquiry.query.filter_by(
        student_id=student.id
    ).order_by(desc(Inquiry.created_at)).limit(5).all()
    
    # Get today's activities
    todays_activities = []
    
    # Add counseling sessions for today
    today_sessions = CounselingSession.query.filter(
        CounselingSession.student_id == student.id,
        CounselingSession.scheduled_at >= today.replace(hour=0, minute=0, second=0),
        CounselingSession.scheduled_at <= today.replace(hour=23, minute=59, second=59)
    ).all()
    
    for session in today_sessions:
        todays_activities.append({
            'type': 'counseling',
            'description': f"Counseling session with {session.office.name} at {session.scheduled_at.strftime('%I:%M %p')}",
            'time': session.scheduled_at,
            'link_url': url_for('student.view_session', session_id=session.id)
        })
    
    # Add recent inquiry updates for today
    today_inquiries = Inquiry.query.filter(
        Inquiry.student_id == student.id,
        Inquiry.created_at >= today.replace(hour=0, minute=0, second=0),
        Inquiry.created_at <= today.replace(hour=23, minute=59, second=59)
    ).all()
    
    for inquiry in today_inquiries:
        status_text = "updated"
        if inquiry.status == 'resolved':
            status_text = "resolved"
        elif inquiry.status == 'in_progress':
            status_text = "in progress"
            
        todays_activities.append({
            'type': 'inquiry',
            'description': f"Inquiry '{inquiry.subject}' was {status_text}",
            'time': inquiry.created_at or inquiry.created_at,
            'link_url': url_for('student.view_inquiry', inquiry_id=inquiry.id)
        })
    
    # Sort activities by time
    todays_activities.sort(key=lambda x: x['time'], reverse=True)
    
    # Get recent announcements
    recent_announcements = Announcement.query.order_by(
        desc(Announcement.created_at)
    ).limit(3).all()
    
    for announcement in recent_announcements:
        # Mark announcement as new if it's less than 3 days old
        announcement.is_new = (today - announcement.created_at).days < 3
    
    # Get available offices for creating inquiries and sessions
    # Since 'is_active' does not exist, fetch all offices instead
    available_offices = Office.query.all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Record this dashboard view as activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed dashboard",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/student_dashboard.html',
        today=today,
        stats=stats,
        upcoming_schedule=upcoming_schedule,
        recent_inquiries=recent_inquiries,
        todays_activities=todays_activities,
        recent_announcements=recent_announcements,
        available_offices=available_offices,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )