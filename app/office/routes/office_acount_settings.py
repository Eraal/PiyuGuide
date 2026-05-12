from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, Notification
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import time  
import os
import re
from sqlalchemy import func, case, desc, or_  
from app.office import office_bp
from app.utils import role_required
from app.office.routes.office_dashboard import get_office_context


# Forms for account settings
class PersonalInfoForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=1, max=50)])
    middle_name = StringField('Middle Name', validators=[Length(max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=100)])

class PasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(), 
        Length(min=8, message="Password must be at least 8 characters long")
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(), 
        EqualTo('new_password', message="Passwords must match")
    ])

class ProfilePictureForm(FlaskForm):
    profile_pic = FileField('Profile Picture', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])

class NotificationPreferencesForm(FlaskForm):
    video_call_notifications = BooleanField('Video Call Notifications')
    video_call_email_reminders = BooleanField('Email Reminders')
    preferred_video_quality = SelectField('Preferred Video Quality', choices=[
        ('auto', 'Auto (Recommended)'),
        ('low', 'Low Quality'),
        ('medium', 'Medium Quality'),
        ('high', 'High Quality')
    ])


@office_bp.route('/office-account-settings')
@login_required
@role_required(['office_admin'])
def office_account_settings():
    """Office Admin Account Settings page"""
    personal_form = PersonalInfoForm()
    password_form = PasswordChangeForm()
    profile_pic_form = ProfilePictureForm()
    notification_form = NotificationPreferencesForm()
    
    # Check if 2FA is enabled (placeholder for future implementation)
    tfa_enabled = False  # TODO: Implement 2FA system
    
    # Get context data for the base template
    context = get_office_context()
    
    return render_template('office/account_settings.html',
                         personal_form=personal_form,
                         password_form=password_form,
                         profile_pic_form=profile_pic_form,
                         notification_form=notification_form,
                         tfa_enabled=tfa_enabled,
                         **context)


@office_bp.route('/update-personal-info', methods=['POST'])
@login_required
@role_required(['office_admin'])
def update_personal_info():
    """Update personal information"""
    form = PersonalInfoForm()
    
    if form.validate_on_submit():
        try:
            # Check if email is already taken by another user
            existing_user = User.query.filter(
                User.email == form.email.data,
                User.id != current_user.id
            ).first()
            
            if existing_user:
                flash('Email address is already in use by another account.', 'error')
                return redirect(url_for('office.office_account_settings'))
            
            # Update user information
            current_user.first_name = form.first_name.data
            current_user.middle_name = form.middle_name.data if form.middle_name.data else None
            current_user.last_name = form.last_name.data
            current_user.email = form.email.data
            
            db.session.commit()
            flash('Personal information updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your information. Please try again.', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
    
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/change-password', methods=['POST'])
@login_required
@role_required(['office_admin'])
def change_password():
    """Change user password"""
    form = PasswordChangeForm()
    
    if form.validate_on_submit():
        try:
            # Verify current password
            if not check_password_hash(current_user.password_hash, form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('office.office_account_settings'))
            
            # Validate new password strength
            new_password = form.new_password.data
            if not validate_password_strength(new_password):
                flash('Password must contain at least one letter, one number, and one special character.', 'error')
                return redirect(url_for('office.office_account_settings'))
            
            # Update password
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while changing your password. Please try again.', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
    
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/update-profile-picture', methods=['POST'])
@login_required
@role_required(['office_admin'])
def update_profile_picture():
    """Update profile picture"""
    form = ProfilePictureForm()
    
    if form.validate_on_submit():
        try:
            file = form.profile_pic.data
            if file:
                # Secure the filename
                filename = secure_filename(file.filename)
                
                # Generate unique filename
                timestamp = int(time.time())
                name, ext = os.path.splitext(filename)
                unique_filename = f"office_admin_{current_user.id}_{timestamp}{ext}"
                
                # Define upload path
                upload_path = os.path.join('static', 'uploads', 'profile_pics')
                os.makedirs(upload_path, exist_ok=True)
                
                # Save the file
                file_path = os.path.join(upload_path, unique_filename)
                file.save(file_path)
                
                # Remove old profile picture if exists
                if current_user.profile_pic:
                    old_file_path = os.path.join(upload_path, current_user.profile_pic)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                
                # Update user profile picture
                current_user.profile_pic = unique_filename
                db.session.commit()
                
                flash('Profile picture updated successfully!', 'success')
            else:
                flash('No file selected.', 'error')
                
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while uploading your profile picture. Please try again.', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
    
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/remove-profile-picture', methods=['POST'])
@login_required
@role_required(['office_admin'])
def remove_profile_picture():
    """Remove profile picture"""
    try:
        if current_user.profile_pic:
            # Remove file from filesystem
            upload_path = os.path.join('static', 'uploads', 'profile_pics')
            file_path = os.path.join(upload_path, current_user.profile_pic)
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Remove from database
            current_user.profile_pic = None
            db.session.commit()
            
            flash('Profile picture removed successfully!', 'success')
        else:
            flash('No profile picture to remove.', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while removing your profile picture. Please try again.', 'error')
    
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/update-notification-preferences', methods=['POST'])
@login_required
@role_required(['office_admin'])
def update_notification_preferences():
    """Update notification preferences"""
    form = NotificationPreferencesForm()
    
    if form.validate_on_submit():
        try:
            # Update notification preferences
            current_user.video_call_notifications = form.video_call_notifications.data
            current_user.video_call_email_reminders = form.video_call_email_reminders.data
            current_user.preferred_video_quality = form.preferred_video_quality.data
            
            db.session.commit()
            flash('Notification preferences updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your preferences. Please try again.', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
    
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/deactivate-account', methods=['POST'])
@login_required
@role_required(['office_admin'])
def deactivate_account():
    """Deactivate user account"""
    try:
        reason = request.form.get('deactivation_reason', '').strip()
        
        # Deactivate account
        current_user.is_active = False
        
        # Log the deactivation (optional - create audit log entry)
        # audit_log = AuditLog(
        #     user_id=current_user.id,
        #     action='account_deactivated',
        #     details=f'User deactivated their own account. Reason: {reason}' if reason else 'User deactivated their own account',
        #     timestamp=datetime.utcnow()
        # )
        # db.session.add(audit_log)
        
        db.session.commit()
        
        flash('Your account has been deactivated. Contact an administrator to reactivate it.', 'info')
        
        # Redirect to logout
        return redirect(url_for('auth.logout'))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deactivating your account. Please try again.', 'error')
        return redirect(url_for('office.office_account_settings'))


# Placeholder routes for future features
@office_bp.route('/setup-two-factor')
@login_required
@role_required(['office_admin'])
def setup_two_factor():
    """Setup two-factor authentication (placeholder)"""
    flash('Two-factor authentication setup is not yet implemented.', 'info')
    return redirect(url_for('office.office_account_settings'))


@office_bp.route('/disable-two-factor', methods=['POST'])
@login_required
@role_required(['office_admin'])
def disable_two_factor():
    """Disable two-factor authentication (placeholder)"""
    return jsonify({'success': False, 'message': 'Two-factor authentication is not yet implemented.'})


@office_bp.route('/login-history')
@login_required
@role_required(['office_admin'])
def login_history():
    """View login history (placeholder)"""
    flash('Login history feature is not yet implemented.', 'info')
    return redirect(url_for('office.office_account_settings'))


def validate_password_strength(password):
    """Validate password strength"""
    # Check for at least one letter, one number, and one special character
    has_letter = re.search(r'[a-zA-Z]', password)
    has_number = re.search(r'\d', password)
    has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
    
    return bool(has_letter and has_number and has_special)