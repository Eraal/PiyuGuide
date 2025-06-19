from app.models import (Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, 
                        CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
                        OfficeLoginLog, AuditLog, ConcernType, OfficeConcernType)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp

################################# EDIT ADMIN ###############################################

@admin_bp.route('/edit_office_admin/<int:admin_id>/', methods=['GET', 'POST'])
@login_required
def edit_office_admin(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    
    # Get all offices for dropdown selection
    offices = Office.query.all()
    
    if request.method == 'POST':
        # Get form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        middle_name = request.form.get('middle_name', '')
        email = request.form.get('email')
        office_id = request.form.get('office_id')
        password = request.form.get('password')
        is_active = 'is_active' in request.form
        reset_password = 'reset_password' in request.form
        unlock_account = 'unlock_account' in request.form
        
        # Validate required fields
        if not all([first_name, last_name, email, office_id]):
            flash('Please fill all required fields.', 'error')
            return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)
        
        # Check if email already exists for another user
        existing_user = User.query.filter(User.email == email, User.id != office_admin.user_id).first()
        if existing_user:
            flash('Email already in use by another user.', 'error')
            return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)
        
        # Update user information
        office_admin.user.first_name = first_name
        office_admin.user.last_name = last_name
        office_admin.user.middle_name = middle_name
        office_admin.user.email = email
        office_admin.user.is_active = is_active
        
        # Handle password update if provided
        if password:
            office_admin.user.password_hash = generate_password_hash(password)
            
        # Handle password reset flag
        if reset_password:
            office_admin.user.require_password_reset = True
        
        # Handle account unlock
        if unlock_account and office_admin.user.account_locked:
            office_admin.user.unlock_account(current_user, reason="Administrative unlock")
        
        # Update office assignment
        if int(office_id) != office_admin.office_id:
            office_admin.office_id = int(office_id)
        
        # Handle profile picture upload
        if 'profile_pic' in request.files and request.files['profile_pic'].filename != '':
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{office_admin.user_id}_{file.filename}")
                
                # Get upload folder from config, making sure it's properly imported
                try:
                    from flask import current_app
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_pics', filename)
                
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    
                    file.save(filepath)
                    office_admin.user.profile_pic = f"/static/uploads/profile_pics/{filename}"
                except Exception as e:
                    flash(f'Error uploading profile picture: {str(e)}', 'error')
        
        # Log the admin action using SuperAdminActivityLog
        super_admin_log = SuperAdminActivityLog(
            super_admin_id=current_user.id,
            action=f"Updated admin: {office_admin.user.get_full_name()}",
            target_type='user',
            target_user_id=office_admin.user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(super_admin_log)
        
        # Create audit log entry using the correct fields for AuditLog model
        audit_log = AuditLog.log_action(
            actor=current_user,
            action="Updated Office Admin",
            target_type="user",
            status=f"Updated {office_admin.user.get_full_name()}",
            is_success=True
        )
        
        try:
            db.session.commit()
            flash('Admin information updated successfully.', 'success')
            return redirect(url_for('admin.view_admin_details', admin_id=admin_id))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'error')
    
    return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)