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

################################# EDIT OFFICE ###############################################

@admin_bp.route('/edit-office/<int:office_id>', methods=['GET', 'POST'])
@login_required
def edit_office(office_id):
    """Edit existing office details including supported concern types"""
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office = Office.query.get_or_404(office_id)
    concern_types = ConcernType.query.all()
    
    # Get currently supported concern types for this office
    office_concerns = OfficeConcernType.query.filter_by(office_id=office_id).all()
    supported_concern_ids = [oc.concern_type_id for oc in office_concerns]
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        supports_video = request.form.get('supports_video', False)
        
        # Concern type handling:
        # Previously, if the edit form did NOT include any checked concern checkboxes, the
        # submitted POST contained zero 'concern_types' entries. The prior logic interpreted
        # an empty list as an instruction to delete ALL existing office concern associations,
        # which caused "Nature of Concern" entries to *disappear* when a super admin edited
        # only basic office fields (name/description/video) via a simplified form that lacked
        # concern checkboxes.
        #
        # To prevent unintended data loss, we now only modify concern associations when at
        # least one 'concern_types' field is present in the submitted form (i.e., the user
        # explicitly interacted with concern checkboxes). This preserves existing concern
        # links for edit forms that do not expose them.
        concern_fields_present = any(key == 'concern_types' for key in request.form.keys())
        if concern_fields_present:
            selected_concern_ids = [int(id) for id in request.form.getlist('concern_types')]
        else:
            selected_concern_ids = None  # Sentinel indicating: do NOT change associations
        
        # Check if office with same name already exists (excluding this one)
        existing_office = Office.query.filter(Office.name == name, Office.id != office_id).first()
        if existing_office:
            flash('An office with this name already exists.', 'error')
            return render_template('admin/edit_office.html', 
                                  office=office, 
                                  concern_types=concern_types, 
                                  supported_concern_ids=supported_concern_ids)
        
        # Update basic office details
        old_name = office.name
        office.name = name
        office.description = description
        office.supports_video = supports_video == 'true'
        
        # Update concern associations only if explicitly submitted
        if selected_concern_ids is not None:
            # Remove ones that are no longer selected
            for office_concern in office_concerns:
                if office_concern.concern_type_id not in selected_concern_ids:
                    db.session.delete(office_concern)

            # Add newly selected concern types
            for concern_id in selected_concern_ids:
                if concern_id not in supported_concern_ids:
                    new_office_concern = OfficeConcernType(
                        office_id=office_id,
                        concern_type_id=concern_id
                    )
                    db.session.add(new_office_concern)
        
        # Log activity
        log = SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action="Updated office",
            target_type="office",
            target_office=office,
            details=f"Updated office from '{old_name}' to '{name}'",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        # Add to general audit log
        audit_log = AuditLog.log_action(
            actor=current_user,
            action="Updated Office",
            target_type="office",
            office=office,
            status="active",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        try:
            db.session.commit()
            flash('Office updated successfully!', 'success')
            return redirect(url_for('admin.office_stats'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating the office: {str(e)}', 'error')
    
    return render_template('admin/edit_office.html', 
                          office=office, 
                          concern_types=concern_types, 
                          supported_concern_ids=supported_concern_ids)

# Toggle Office Status (Modified since Office doesn't have is_active field directly)
@admin_bp.route('/office/<int:office_id>/toggle_status/', methods=['POST'])
@login_required
def toggle_office_status(office_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office = Office.query.get_or_404(office_id)
    
    # Since Office doesn't have is_active field, we'll handle it differently
    # We could implement this by checking if an office has any active admins
    has_active_admins = False
    for admin in office.office_admins:
        if admin.user.is_active:
            has_active_admins = True
            break
    
    status_text = "disabled" if has_active_admins else "enabled"
    action_text = "Disabled" if has_active_admins else "Enabled"
    
    # If we want to disable the office, we'll deactivate all admin accounts
    if has_active_admins:
        for admin in office.office_admins:
            admin.user.is_active = False
    else:
        # If we want to enable, we need to ensure there's at least one active admin
        # If none, we'll notify the user
        if not office.office_admins:
            flash('Cannot enable office without assigned admins.', 'warning')
            return redirect(url_for('admin.office_stats'))
        # Otherwise, activate the first admin
        office.office_admins[0].user.is_active = True
    
    # Log activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"{action_text} office: {office.name}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        flash(f'Office {status_text} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while updating the office status: {str(e)}', 'error')
    
    return redirect(url_for('admin.office_stats'))