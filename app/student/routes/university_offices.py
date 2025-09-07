from flask import render_template, redirect, url_for, flash, request, session
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
    
    # Resolve campus context: prefer student's campus, fallback to session-selected campus
    campus_id = student.campus_id or session.get('selected_campus_id')
    # Get offices only for the resolved campus; if unknown, fallback to all to avoid empty view
    offices = Office.query.filter_by(campus_id=campus_id).all() if campus_id else Office.query.all()
    
    # Get offices that support video counseling
    video_offices = [office for office in offices if office.supports_video]
    
    # Calculate statistics
    total_offices = len(offices)
    video_services_count = len(video_offices)
    
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
        total_offices=total_offices,
        video_services_count=video_services_count,
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
    
    # Ensure the office is within the student's campus (fallback to session campus)
    campus_id = student.campus_id or session.get('selected_campus_id')
    if campus_id and office.campus_id != campus_id:
        flash('You can only view offices from your campus.', 'error')
        return redirect(url_for('student.university_offices'))
    
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