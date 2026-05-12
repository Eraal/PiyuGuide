from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog, Announcement
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp

################################# ADMIN DETAIL ###############################################

@admin_bp.route('/office_admin/<int:admin_id>/')
@login_required
def view_admin_details(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    
    # Get messages using query since we need to order and limit them
    inquiry_messages = InquiryMessage.query.filter_by(sender_id=office_admin.user_id).order_by(
        InquiryMessage.created_at.desc()).limit(5).all()
    
    # For announcements, we need to query directly from the Announcement model
    # since the relationship is now eagerly loaded (not a query object)
    announcements = Announcement.query.filter_by(author_id=office_admin.user_id).order_by(
        Announcement.created_at.desc()).limit(3).all()
    
    # Get counseling sessions
    counseling_sessions = CounselingSession.query.filter_by(counselor_id=office_admin.user_id).all()
    
    # Create a dictionary of counts to pass to the template
    counts = {
        'inquiry_messages': len(inquiry_messages),
        'announcements': len(announcements),
        'counseling_sessions': len(counseling_sessions)
    }
    
    # Get admin login logs for activity history
    admin_logs = OfficeLoginLog.query.filter_by(office_admin_id=admin_id).order_by(
        OfficeLoginLog.login_time.desc()).limit(10).all()
    
    # Get inquiries for the office
    inquiries = Inquiry.query.filter_by(office_id=office_admin.office_id).all()
    
    # Log super admin activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Viewed details for admin: {office_admin.user.get_full_name()}",
        target_type='user',  # Added target_type field which is required in the model
        target_user_id=office_admin.user_id,  # Added target user reference
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    
    return render_template('admin/admin_detail.html', 
                          admin=office_admin,
                          inquiry_messages=inquiry_messages,
                          announcements=announcements,
                          counseling_sessions=counseling_sessions,
                          counts=counts,
                          admin_logs=admin_logs,
                          inquiries=inquiries)

