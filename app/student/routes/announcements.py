from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc
from app.student import student_bp
from app.models import (
    Announcement, Student, User, Office, 
    StudentActivityLog, Notification
)
from app.extensions import db
from app.utils import role_required

@student_bp.route('/announcements')
@login_required
@role_required(['student'])
def announcements():
    """View all announcements available to the student"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get announcements (both public and specific to offices the student has inquired to)
    # First, get all offices the student has inquired to
    from app.models import Inquiry
    inquiry_offices = db.session.query(Inquiry.office_id).filter_by(student_id=student.id).distinct().all()
    office_ids = [office[0] for office in inquiry_offices]
    
    # Get public announcements and announcements for those offices
    announcements = Announcement.query.filter(
        (Announcement.is_public == True) | 
        (Announcement.target_office_id.in_(office_ids))
    ).order_by(desc(Announcement.created_at)).all()
    
    # Mark recent announcements (less than 3 days old)
    today = datetime.utcnow()
    for announcement in announcements:
        announcement.is_new = (today - announcement.created_at).days < 3
    
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
        action="Viewed announcements",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/announcements.html',
        announcements=announcements,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

@student_bp.route('/announcement/<int:announcement_id>')
@login_required
@role_required(['student'])
def view_announcement(announcement_id):
    """View details for a specific announcement"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the announcement
    announcement = Announcement.query.get_or_404(announcement_id)
    
    # Check if student is allowed to see this announcement
    if not announcement.is_public:
        # Check if student has inquired to the office this announcement is for
        from app.models import Inquiry
        has_inquiry = Inquiry.query.filter_by(
            student_id=student.id,
            office_id=announcement.target_office_id
        ).first()
        
        if not has_inquiry:
            flash("You do not have permission to view this announcement", "error")
            return redirect(url_for('student.announcements'))
    
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
        action=f"Viewed announcement #{announcement_id}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/view_announcement.html',
        announcement=announcement,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )