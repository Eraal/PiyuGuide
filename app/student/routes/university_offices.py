from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import desc

from app.student import student_bp
from app.models import Office, Notification, Student, StudentActivityLog
from app.utils import role_required
from app.extensions import db

from datetime import datetime

@student_bp.route('/university-offices')
@login_required
@role_required(['student'])
def university_offices():
    """View the list of available university offices and their details"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get all offices
    offices = Office.query.all()
    
    # Get offices that support video counseling
    video_offices = [office for office in offices if office.supports_video]
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed university offices",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/university_offices.html',
        offices=offices,
        video_offices=video_offices,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

@student_bp.route('/university-offices/<int:office_id>')
@login_required
@role_required(['student'])
def view_office_detail(office_id):
    """View details for a specific university office"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the office
    office = Office.query.get_or_404(office_id)
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Viewed office details: {office.name}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/office_detail.html',
        office=office,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )