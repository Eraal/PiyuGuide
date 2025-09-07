from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc
from app.student import student_bp
from app.models import (
    Student, User, Inquiry, CounselingSession,
    Notification, StudentActivityLog, Campus
)
from app.extensions import db
from app.utils import role_required

# New imports for forms & file handling
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, BooleanField, SelectField, PasswordField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, EqualTo
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os, time, re


# -------------------- Forms --------------------
class StudentPersonalInfoForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=50)])
    middle_name = StringField('Middle Name', validators=[Optional(), Length(max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=100)])
    student_number = StringField('Student Number', validators=[Optional(), Length(max=50)])  # usually read-only
    department_id = SelectField('Department', coerce=int, validators=[Optional()])
    section = StringField('Section', validators=[Optional(), Length(max=50)])
    year_level = StringField('Year Level', validators=[Optional(), Length(max=20)])

class StudentProfilePictureForm(FlaskForm):
    profile_pic = FileField('Profile Picture', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])

class StudentNotificationPreferencesForm(FlaskForm):
    video_call_notifications = BooleanField('Video Call Notifications')
    video_call_email_reminders = BooleanField('Email Reminders')
    preferred_video_quality = SelectField('Preferred Video Quality', choices=[
        ('auto', 'Auto (Recommended)'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ])

class StudentPasswordChangeForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(), Length(min=8, message='Must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('new_password', message='Passwords must match')
    ])

class StudentDeactivateAccountForm(FlaskForm):
    reason = TextAreaField('Reason (optional)', validators=[Optional(), Length(max=255)])


def _validate_password_strength(password: str) -> bool:
    """Basic password strength validator (not yet exposed in UI)."""
    if not password:
        return False
    has_letter = re.search(r'[A-Za-z]', password)
    has_number = re.search(r'[0-9]', password)
    has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
    return bool(has_letter and has_number and has_special and len(password) >= 8)

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
    """Comprehensive account settings page for students."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()

    # Prefill forms
    personal_form = StudentPersonalInfoForm(
        first_name=current_user.first_name,
        middle_name=current_user.middle_name,
        last_name=current_user.last_name,
        email=current_user.email,
        student_number=student.student_number,
        department_id=student.department_id,
        section=student.section,
        year_level=student.year_level
    )

    # Populate department choices based on student's campus
    from app.models import Department
    dept_choices = []
    if student.campus_id:
        depts = Department.query.filter_by(campus_id=student.campus_id, is_active=True).order_by(Department.name.asc()).all()
        dept_choices = [(d.id, d.name) for d in depts]
    personal_form.department_id.choices = [(0, '— Select Department —')] + dept_choices

    notif_form = StudentNotificationPreferencesForm(
        video_call_notifications=current_user.video_call_notifications,
        video_call_email_reminders=current_user.video_call_email_reminders,
        preferred_video_quality=current_user.preferred_video_quality
    )

    pic_form = StudentProfilePictureForm()
    password_form = StudentPasswordChangeForm()
    deactivate_form = StudentDeactivateAccountForm()

    # Navbar / notifications context
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(desc(Notification.created_at)).limit(5).all()

    # Activity log
    log_entry = StudentActivityLog(
        student_id=student.id,
        action='Viewed account settings page',
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()

    campus = None
    if student.campus_id:
        campus = Campus.query.get(student.campus_id)

    return render_template(
        'student/account_settings.html',
        student=student,
        campus=campus,
        personal_form=personal_form,
    notif_form=notif_form,
    password_form=password_form,
    deactivate_form=deactivate_form,
        pic_form=pic_form,
        notifications=notifications,
        unread_notifications_count=unread_notifications_count
    )


# -------------------- Update Endpoints --------------------
@student_bp.route('/update-personal-info', methods=['POST'])
@login_required
@role_required(['student'])
def update_personal_info():
    """Update student's personal & academic info."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    form = StudentPersonalInfoForm()

    # Ensure department choices are populated for validation
    from app.models import Department
    dept_choices = []
    if student.campus_id:
        depts = Department.query.filter_by(campus_id=student.campus_id, is_active=True).order_by(Department.name.asc()).all()
        dept_choices = [(d.id, d.name) for d in depts]
    form.department_id.choices = [(0, '— Select Department —')] + dept_choices

    if form.validate_on_submit():
        try:
            # Unique email check
            existing = User.query.filter(User.email == form.email.data, User.id != current_user.id).first()
            if existing:
                flash('Email is already used by another account.', 'error')
                return redirect(url_for('student.account_settings'))

            # Update user core fields
            current_user.first_name = form.first_name.data.strip()
            current_user.middle_name = form.middle_name.data.strip() if form.middle_name.data else None
            current_user.last_name = form.last_name.data.strip()
            current_user.email = form.email.data.strip()

            # Update student-specific fields (student_number often read-only; only update if previously empty)
            if not student.student_number and form.student_number.data:
                student.student_number = form.student_number.data.strip()
            # Update structured department if provided
            if form.department_id.data and form.department_id.data != 0:
                student.department_id = form.department_id.data
                # Keep legacy text in sync for compatibility
                from app.models import Department
                d = Department.query.get(form.department_id.data)
                student.department = d.name if d else None
            student.section = form.section.data.strip() if form.section.data else None
            student.year_level = form.year_level.data.strip() if form.year_level.data else None

            db.session.commit()

            StudentActivityLog.log_action(
                student, 'Updated personal information', ip_address=request.remote_addr, user_agent=request.user_agent.string
            )
            db.session.commit()
            flash('Information updated successfully.', 'success')
        except Exception:
            db.session.rollback()
            flash('An error occurred while saving changes.', 'error')
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f'{field}: {err}', 'error')

    return redirect(url_for('student.account_settings'))


@student_bp.route('/update-profile-picture', methods=['POST'])
@login_required
@role_required(['student'])
def update_profile_picture():
    """Upload/update profile picture for student."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    form = StudentProfilePictureForm()
    if form.validate_on_submit() and form.profile_pic.data:
        try:
            file = form.profile_pic.data
            filename = secure_filename(file.filename)
            if not filename:
                flash('Invalid file selected.', 'error')
                return redirect(url_for('student.account_settings'))
            # Size validation (2MB limit)
            file.stream.seek(0, os.SEEK_END)
            size = file.stream.tell()
            file.stream.seek(0)
            max_bytes = 2 * 1024 * 1024
            if size > max_bytes:
                flash('Image exceeds 2MB size limit.', 'error')
                return redirect(url_for('student.account_settings'))
            ts = int(time.time())
            base, ext = os.path.splitext(filename)
            unique = f"student_{current_user.id}_{ts}{ext.lower()}"
            upload_dir = os.path.join('static', 'uploads', 'profile_pics')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, unique)
            file.save(file_path)

            # Remove old
            if current_user.profile_pic:
                old_path = os.path.join(upload_dir, current_user.profile_pic)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass

            current_user.profile_pic = unique
            db.session.commit()

            StudentActivityLog.log_action(
                student, 'Updated profile picture', ip_address=request.remote_addr, user_agent=request.user_agent.string
            )
            db.session.commit()
            flash('Profile picture updated.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to upload profile picture.', 'error')
    else:
        if form.errors:
            for field, errors in form.errors.items():
                for err in errors:
                    flash(f'{field}: {err}', 'error')
        else:
            flash('No file selected.', 'error')
    return redirect(url_for('student.account_settings'))


@student_bp.route('/update-notification-preferences', methods=['POST'])
@login_required
@role_required(['student'])
def update_notification_preferences():
    """Update student's notification/video preferences."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    form = StudentNotificationPreferencesForm()
    if form.validate_on_submit():
        try:
            current_user.video_call_notifications = form.video_call_notifications.data
            current_user.video_call_email_reminders = form.video_call_email_reminders.data
            current_user.preferred_video_quality = form.preferred_video_quality.data
            db.session.commit()
            StudentActivityLog.log_action(
                student, 'Updated notification preferences', ip_address=request.remote_addr, user_agent=request.user_agent.string
            )
            db.session.commit()
            flash('Preferences updated.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to save preferences.', 'error')
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f'{field}: {err}', 'error')
    return redirect(url_for('student.account_settings'))


@student_bp.route('/change-password', methods=['POST'])
@login_required
@role_required(['student'])
def change_password():
    """Allow student to change password."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    form = StudentPasswordChangeForm()
    if form.validate_on_submit():
        try:
            if not check_password_hash(current_user.password_hash, form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('student.account_settings'))
            new_pw = form.new_password.data
            if not _validate_password_strength(new_pw):
                flash('Password must contain letters, numbers & special character.', 'error')
                return redirect(url_for('student.account_settings'))
            current_user.password_hash = generate_password_hash(new_pw)
            db.session.commit()
            StudentActivityLog.log_action(
                student, 'Changed password', ip_address=request.remote_addr, user_agent=request.user_agent.string
            )
            db.session.commit()
            flash('Password updated successfully.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to change password.', 'error')
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f'{field}: {err}', 'error')
    return redirect(url_for('student.account_settings'))


@student_bp.route('/deactivate-account', methods=['POST'])
@login_required
@role_required(['student'])
def deactivate_account():
    """Student self-deactivation."""
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    form = StudentDeactivateAccountForm()
    if form.validate_on_submit():
        try:
            current_user.is_active = False
            db.session.commit()
            StudentActivityLog.log_action(
                student, 'Deactivated account', ip_address=request.remote_addr, user_agent=request.user_agent.string
            )
            db.session.commit()
            flash('Account deactivated. Contact admin to reactivate.', 'info')
            return redirect(url_for('auth.logout'))
        except Exception:
            db.session.rollback()
            flash('Failed to deactivate account.', 'error')
    else:
        for field, errors in form.errors.items():
            for err in errors:
                flash(f'{field}: {err}', 'error')
    return redirect(url_for('student.account_settings'))
