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
from app.utils.decorators import campus_access_required

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

def allowed_file(filename: str) -> bool:
    """Basic whitelist for profile picture uploads by extension."""
    if not filename:
        return False
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_IMAGE_EXTENSIONS

################################# EDIT ADMIN ###############################################

@admin_bp.route('/edit_office_admin/<int:admin_id>/', methods=['GET', 'POST'])
@login_required
@campus_access_required
def edit_office_admin(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    
    # Get offices for current campus only
    campus_id = getattr(current_user, 'campus_id', None)
    offices = Office.query.filter_by(campus_id=campus_id).all() if campus_id else []

    # Normalize any legacy stored profile_pic path (leading /static/)
    if office_admin.user.profile_pic and office_admin.user.profile_pic.startswith('/static/'):
        try:
            office_admin.user.profile_pic = office_admin.user.profile_pic[len('/static/'):]
            db.session.commit()
        except Exception:
            db.session.rollback()
    
    if request.method == 'POST':
        # Get form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        middle_name = request.form.get('middle_name', '')
        email = request.form.get('email')
        office_id = request.form.get('office_id')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
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
            if password_confirm and password != password_confirm:
                flash('Passwords do not match.', 'error')
                return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)
            if len(password) < 8:
                flash('Password must be at least 8 characters long.', 'error')
                return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)
            office_admin.user.password_hash = generate_password_hash(password)
            
        # Handle password reset flag
        if reset_password:
            # Only set the flag if the model supports it (future-proofing)
            if hasattr(office_admin.user, 'require_password_reset'):
                office_admin.user.require_password_reset = True
            else:
                flash('Password reset flag not currently supported for this user type.', 'info')
        
        # Handle account unlock
        if unlock_account and office_admin.user.account_locked:
            office_admin.user.unlock_account(current_user, reason="Administrative unlock")
        
        # Update office assignment (validate campus)
        if int(office_id) != office_admin.office_id:
            new_office = Office.query.get(int(office_id))
            if not new_office or (campus_id and new_office.campus_id != campus_id):
                flash('Selected office is not part of your campus.', 'error')
                return render_template('admin/edit_admin_detail.html', admin=office_admin, offices=offices)
            office_admin.office_id = int(office_id)
        
        # Handle profile picture upload
        if 'profile_pic' in request.files and request.files['profile_pic'].filename:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                # Normalise any prior stored path that incorrectly began with /static/
                existing_path = office_admin.user.profile_pic or ''
                if existing_path.startswith('/static/'):
                    # Trim leading /static/ so future url_for('static', filename=...) works
                    office_admin.user.profile_pic = existing_path[len('/static/'):]  # not persisted until commit
                filename = secure_filename(f"{office_admin.user_id}_{file.filename}")
                try:
                    from flask import current_app
                    upload_root = current_app.config.get('UPLOAD_FOLDER')
                    profile_dir = os.path.join(upload_root, 'profile_pics')
                    os.makedirs(profile_dir, exist_ok=True)

                    # Remove old file (best effort) if it exists and is within our upload root
                    if existing_path and not existing_path.startswith('/static/') and 'uploads/profile_pics/' in existing_path:
                        old_abs = os.path.join(current_app.root_path, 'static', existing_path)
                        try:
                            if os.path.isfile(old_abs):
                                os.remove(old_abs)
                        except Exception:
                            pass

                    abs_path = os.path.join(profile_dir, filename)
                    file.save(abs_path)

                    # Store relative path (no leading /static/) so templates using url_for('static', filename=...) work
                    office_admin.user.profile_pic = f"uploads/profile_pics/{filename}"
                except Exception as e:
                    flash(f'Error uploading profile picture: {str(e)}', 'error')
            else:
                flash('Invalid image file type. Allowed: png, jpg, jpeg, gif, webp', 'error')
        
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