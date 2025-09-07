from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, 
    CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, ConcernType, OfficeConcernType, InquiryConcern
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp


@admin_bp.route('/concern-types', methods=['GET', 'POST'])
@login_required
def manage_concern_types():
    """Page to manage concern types that offices can support"""
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get all existing concern types
    concern_types = ConcernType.query.order_by(ConcernType.name).all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            # Add new concern type
            name = request.form.get('name').strip()
            description = request.form.get('description').strip()
            allows_other = request.form.get('allows_other', False) == 'true'
            
            # Check if concern type with same name already exists
            existing_type = ConcernType.query.filter(func.lower(ConcernType.name) == func.lower(name)).first()
            if existing_type:
                flash(f'A concern type with the name "{name}" already exists.', 'error')
            else:
                new_concern = ConcernType(
                    name=name,
                    description=description,
                    allows_other=allows_other
                )
                db.session.add(new_concern)
                
                # Log action
                log = SuperAdminActivityLog.log_action(
                    super_admin=current_user,
                    action="Created concern type",
                    target_type="concern_type",
                    details=f"Created concern type: {name}",
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                
                try:
                    db.session.commit()
                    flash(f'Concern type "{name}" added successfully.', 'success')
                    return redirect(url_for('admin.manage_concern_types'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'edit':
            # Edit existing concern type
            concern_id = request.form.get('concern_id')
            name = request.form.get('name').strip()
            description = request.form.get('description').strip()
            allows_other = request.form.get('allows_other', False) == 'true'
            
            concern = ConcernType.query.get(concern_id)
            if not concern:
                flash('Concern type not found.', 'error')
            else:
                # Check if new name conflicts with existing (excluding self)
                existing_type = ConcernType.query.filter(
                    func.lower(ConcernType.name) == func.lower(name),
                    ConcernType.id != concern.id
                ).first()
                
                if existing_type:
                    flash(f'A concern type with the name "{name}" already exists.', 'error')
                else:
                    old_name = concern.name
                    concern.name = name
                    concern.description = description
                    concern.allows_other = allows_other
                    
                    # Log action
                    log = SuperAdminActivityLog.log_action(
                        super_admin=current_user,
                        action="Updated concern type",
                        target_type="concern_type",
                        details=f"Updated concern type from '{old_name}' to '{name}'",
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string
                    )
                    
                    try:
                        db.session.commit()
                        flash(f'Concern type "{name}" updated successfully.', 'success')
                        return redirect(url_for('admin.manage_concern_types'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'delete':
            # Delete concern type
            concern_id = request.form.get('concern_id')
            concern = ConcernType.query.get(concern_id)
            
            if not concern:
                flash('Concern type not found.', 'error')
            else:
                # Check if concern is being used by any offices
                office_concerns = OfficeConcernType.query.filter_by(concern_type_id=concern_id).first()
                # Check if concern is being used in any inquiries
                inquiry_concerns = InquiryConcern.query.filter_by(concern_type_id=concern_id).first()
                
                if office_concerns or inquiry_concerns:
                    flash('This concern type cannot be deleted because it is in use.', 'error')
                else:
                    name = concern.name
                    
                    # Log action
                    log = SuperAdminActivityLog.log_action(
                        super_admin=current_user,
                        action="Deleted concern type",
                        target_type="concern_type",
                        details=f"Deleted concern type: {name}",
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string
                    )
                    
                    try:
                        db.session.delete(concern)
                        db.session.commit()
                        flash(f'Concern type "{name}" deleted successfully.', 'success')
                        return redirect(url_for('admin.manage_concern_types'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'auto_reply':
            # Update auto-reply settings for a concern type
            concern_id = request.form.get('concern_id')
            concern = ConcernType.query.get(concern_id)
            if not concern:
                flash('Concern type not found.', 'error')
            else:
                enabled_str = request.form.get('auto_reply_enabled', 'false')
                message = (request.form.get('auto_reply_message') or '').strip()
                enabled = enabled_str in ['true', 'on', '1', 'yes']

                concern.auto_reply_enabled = enabled
                concern.auto_reply_message = message if enabled else None

                # Log action
                SuperAdminActivityLog.log_action(
                    super_admin=current_user,
                    action="Updated auto-reply",
                    target_type="concern_type",
                    details=f"Auto-reply {'enabled' if enabled else 'disabled'} for concern '{concern.name}'",
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )

                try:
                    db.session.commit()
                    flash('Auto-reply settings updated.', 'success')
                    return redirect(url_for('admin.manage_concern_types'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred: {str(e)}', 'error')
    
    return render_template('admin/concern_types.html', concern_types=concern_types)