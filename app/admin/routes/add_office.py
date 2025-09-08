from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, 
    CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, ConcernType, OfficeConcernType, InquiryConcern
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp

################################# ADMIN ACCOUNT SETTINGS ###############################################

# Add Office
@admin_bp.route('/add-office', methods=['GET', 'POST'])
@login_required
def add_office():
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get all available concern types to display in the form
    concern_types = ConcernType.query.all()
    
    if request.method == 'POST':
        # Determine campus for the new office (required)
        campus_id = getattr(current_user, 'campus_id', None)
        if not campus_id:
            # If admin has no campus assigned, block creation to avoid NULL FK
            flash('Your admin account is not assigned to any campus. Please contact a super super admin to assign a campus before creating offices.', 'error')
            return render_template('admin/add_office.html', concern_types=concern_types)

        name = request.form.get('name')
        description = request.form.get('description')
        supports_video = request.form.get('supports_video', False)
        
        # Get selected concern types from the form (multi-select)
        selected_concern_ids = request.form.getlist('concern_types')

        # Check if office with same name already exists (per campus)
        existing_office = Office.query.filter_by(name=name, campus_id=campus_id).first()
        if existing_office:
            flash('An office with this name already exists.', 'error')
            return render_template('admin/add_office.html', concern_types=concern_types)
        
        # Create new office
        new_office = Office(
            name=name,
            description=description,
            supports_video=supports_video == 'true',
            campus_id=campus_id
        )
        
        # Add the office to session
        db.session.add(new_office)
        
        # We need to flush to get the office ID
        db.session.flush()
        
        # Associate selected concern types with the new office (idempotent, inquiries-enabled)
        for concern_id in selected_concern_ids:
            concern_id_int = int(concern_id)
            existing_assoc = OfficeConcernType.query.filter_by(
                office_id=new_office.id,
                concern_type_id=concern_id_int
            ).first()
            if existing_assoc:
                # Ensure inquiries flag is on for newly created office
                existing_assoc.for_inquiries = True
            else:
                db.session.add(OfficeConcernType(
                    office_id=new_office.id,
                    concern_type_id=concern_id_int,
                    for_inquiries=True
                ))
        
        # Log the activity
        log = SuperAdminActivityLog(
            super_admin_id=current_user.id,
            action="Created new office",
            target_type="office",
            target_office_id=new_office.id,
            details=f"Created office '{name}' with {len(selected_concern_ids)} concern types",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        
        # Also add to general audit log
        audit_log = AuditLog.log_action(
            actor=current_user,
            action="Created Office",
            target_type="office",
            office=new_office,
            status="active",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        try:
            db.session.commit()
            flash('Office added successfully!', 'success')
            return redirect(url_for('admin.office_stats'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while adding the office: {str(e)}', 'error')
    
    return render_template('admin/add_office.html', concern_types=concern_types)





