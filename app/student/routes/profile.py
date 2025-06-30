from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc
from app.student import student_bp
from app.models import (
    Student, User, Inquiry, CounselingSession, 
    Notification, StudentActivityLog
)
from app.extensions import db
from app.utils import role_required

@student_bp.route('/profile')
@login_required
@role_required(['student'])
def profile():
    """Display student profile information"""
    # Get the student record for the current user
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get profile statistics
    total_inquiries = Inquiry.query.filter_by(student_id=student.id).count()
    pending_inquiries = Inquiry.query.filter_by(student_id=student.id, status='pending').count()
    resolved_inquiries = Inquiry.query.filter_by(student_id=student.id, status='resolved').count()
    
    total_sessions = CounselingSession.query.filter_by(student_id=student.id).count()
    completed_sessions = CounselingSession.query.filter_by(student_id=student.id, status='completed').count()
    upcoming_sessions = CounselingSession.query.filter_by(student_id=student.id, status='confirmed').count()
    
    # Get recent activities (last 10)
    recent_activities = StudentActivityLog.query.filter_by(
        student_id=student.id
    ).order_by(desc(StudentActivityLog.timestamp)).limit(10).all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get recent notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
      # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action='Viewed profile page',
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template('student/profile.html',
                           student=student,
                           total_inquiries=total_inquiries,
                           pending_inquiries=pending_inquiries,
                           resolved_inquiries=resolved_inquiries,
                           total_sessions=total_sessions,
                           completed_sessions=completed_sessions,
                           upcoming_sessions=upcoming_sessions,
                           recent_activities=recent_activities,
                           notifications=notifications,
                           unread_notifications_count=unread_notifications_count)

@student_bp.route('/account-settings')
@login_required
@role_required(['student'])
def account_settings():
    """Display account settings page (placeholder for future implementation)"""
    # Get the student record for the current user
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get recent notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
      # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action='Viewed account settings page',
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template('student/account_settings.html',
                           student=student,
                           notifications=notifications,
                           unread_notifications_count=unread_notifications_count)
