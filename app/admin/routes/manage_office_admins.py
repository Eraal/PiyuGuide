from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog
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

################################# ADMIN ACCOUNT SETTINGS ###############################################

@admin_bp.route('/manage-office-admins', methods=['GET', 'POST'])
@login_required
@campus_access_required
def manage_office_admins():
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Determine accessible campus for the current campus admin
    campus_id = getattr(current_user, 'campus_id', None)
    if not campus_id:
        flash('Your account is not assigned to a campus. Please contact the system administrator.', 'error')
        return render_template('admin/manage_office_admins.html', offices=[])

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm') or request.form.get('confirm_password')
        office_id = request.form.get('office_id')
        
        # Validate inputs
        if not first_name or not last_name or not email or not password or not office_id:
            flash('All fields are required.', 'error')
            offices = Office.query.filter_by(campus_id=campus_id).all()
            return render_template('admin/manage_office_admins.html', offices=offices)
        
        # Confirm password match (defense-in-depth vs client-side check)
        if password_confirm is not None and password != password_confirm:
            flash("Passwords do not match.", 'error')
            offices = Office.query.filter_by(campus_id=campus_id).all()
            return render_template('admin/manage_office_admins.html', offices=offices)
        
        # Check if user with this email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('A user with this email already exists.', 'error')
            offices = Office.query.filter_by(campus_id=campus_id).all()
            return render_template('admin/manage_office_admins.html', offices=offices)
        
        # Validate office belongs to current campus
        try:
            office_id_int = int(office_id)
        except (TypeError, ValueError):
            flash('Invalid office selected.', 'error')
            offices = Office.query.filter_by(campus_id=campus_id).all()
            return render_template('admin/manage_office_admins.html', offices=offices)
        
        office = Office.query.get(office_id_int)
        if not office or office.campus_id != campus_id:
            flash('Selected office does not belong to your campus.', 'error')
            offices = Office.query.filter_by(campus_id=campus_id).all()
            return render_template('admin/manage_office_admins.html', offices=offices)
        
        # Create new user - automatically activate the account upon creation
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=generate_password_hash(password),
            role='office_admin',
            is_active=True
        )
        
        db.session.add(new_user)
        db.session.flush()  # To get the new user ID
        
        # Create office admin association
        new_admin = OfficeAdmin(user_id=new_user.id, office_id=office_id_int)
        db.session.add(new_admin)
        
        # Log activity
        log = SuperAdminActivityLog(
            super_admin_id=current_user.id,
            action=f"Created new office admin: {first_name} {last_name} for office ID: {office_id_int}",
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        
        try:
            db.session.commit()
            flash('New office admin created, activated, and assigned to office successfully.', 'success')
            return redirect(url_for('admin.office_stats'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while creating the admin: {str(e)}', 'error')
    
    # Only list offices for the current campus
    offices = Office.query.filter_by(campus_id=campus_id).all()
    return render_template('admin/manage_office_admins.html', offices=offices)
