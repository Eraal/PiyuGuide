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

################################# OFFICE STATS ###############################################


@admin_bp.route('/office-stats')
@login_required
@campus_access_required
def office_stats():
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Campus-scoped queries
    campus_id = current_user.campus_id

    # Get all offices for current campus only
    offices = Office.query.filter(Office.campus_id == campus_id).all()
    
    # Get all office admins with their related data for current campus only
    office_admins = (
        OfficeAdmin.query
        .join(User)
        .join(Office)
        .filter(Office.campus_id == campus_id)
        .all()
    )
    
    # Get active offices (those with at least one admin)
    active_offices = []
    for office in offices:
        if office.office_admins:
            active_offices.append(office)
    
    # Get active admins (those whose user account is active)
    active_admins = []
    for admin in office_admins:
        if admin.user.is_active:
            active_admins.append(admin)
    
    # Get unassigned offices (offices with no admins)
    unassigned_offices = []
    for office in offices:
        if not office.office_admins:
            unassigned_offices.append(office)
    
    # Get unassigned admins (users with admin role but not assigned to ANY office globally)
    # First, get all users with admin role
    admin_users = User.query.filter(User.role == 'office_admin').all()
    
    # Then filter out those who are already assigned to any office (across all campuses)
    assigned_admin_ids_global = [oa.user_id for oa in OfficeAdmin.query.all()]
    unassigned_admins = [user for user in admin_users if user.id not in assigned_admin_ids_global]
    
    # Get available admins for assignment
    available_admins = unassigned_admins
    
    # Calculate inquiries breakdown (campus-scoped via Office)
    total_inquiries = (
        db.session.query(func.count(Inquiry.id))
        .join(Office, Inquiry.office_id == Office.id)
        .filter(Office.campus_id == campus_id)
        .scalar() or 0
    )
    pending_inquiries = (
        db.session.query(func.count(Inquiry.id))
        .join(Office, Inquiry.office_id == Office.id)
        .filter(Office.campus_id == campus_id, Inquiry.status == 'pending')
        .scalar() or 0
    )
    in_progress_inquiries = (
        db.session.query(func.count(Inquiry.id))
        .join(Office, Inquiry.office_id == Office.id)
        .filter(Office.campus_id == campus_id, Inquiry.status == 'in_progress')
        .scalar() or 0
    )
    resolved_inquiries = (
        db.session.query(func.count(Inquiry.id))
        .join(Office, Inquiry.office_id == Office.id)
        .filter(Office.campus_id == campus_id, Inquiry.status == 'resolved')
        .scalar() or 0
    )

    # Prepare per-office insights (lightweight aggregation for charts)
    office_insights = []
    for office in offices:
        total = len(office.inquiries) if office.inquiries else 0
        if total == 0:
            # Still include with zeros to keep consistent ordering if needed
            office_insights.append({
                'id': office.id,
                'name': office.name,
                'total': 0,
                'pending': 0,
                'in_progress': 0,
                'resolved': 0,
            })
            continue
        pending = sum(1 for i in office.inquiries if i.status == 'pending')
        in_prog = sum(1 for i in office.inquiries if i.status == 'in_progress')
        resolved = sum(1 for i in office.inquiries if i.status == 'resolved')
        office_insights.append({
            'id': office.id,
            'name': office.name,
            'total': total,
            'pending': pending,
            'in_progress': in_prog,
            'resolved': resolved,
        })

    # Top offices by total inquiries (limit to 6 for visuals)
    office_insights = sorted(office_insights, key=lambda x: x['total'], reverse=True)[:6]
    
    # Log this activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action="Viewed office statistics",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    
    return render_template('admin/office_stats.html', 
                           offices=offices,
                           office_admins=office_admins,
                           active_offices=active_offices,
                           active_admins=active_admins,
                           unassigned_offices=unassigned_offices,
                           unassigned_admins=unassigned_admins,
                           available_admins=available_admins,
                           total_inquiries=total_inquiries,
                           pending_inquiries=pending_inquiries,
                           in_progress_inquiries=in_progress_inquiries,
                           resolved_inquiries=resolved_inquiries,
                           office_insights=office_insights,
                           admins=admin_users) 
                           
@admin_bp.route('/office/<int:office_id>/')
@login_required
@campus_access_required
def view_office_details(office_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office = Office.query.get_or_404(office_id)
    # Ensure office belongs to current super admin campus
    if current_user.role == 'super_admin' and office.campus_id != current_user.campus_id:
        flash('Access denied. You can only access offices in your assigned campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    # Get recent inquiries for this office
    recent_inquiries = Inquiry.query.filter_by(office_id=office_id).order_by(Inquiry.created_at.desc()).limit(10).all()
    
    # Get stats for this office
    inquiry_stats = {
        'total': Inquiry.query.filter_by(office_id=office_id).count(),
        'pending': Inquiry.query.filter_by(office_id=office_id, status='pending').count(),
        'in_progress': Inquiry.query.filter_by(office_id=office_id, status='in_progress').count(),
        'resolved': Inquiry.query.filter_by(office_id=office_id, status='resolved').count(),
    }
    
    # Get unassigned admins (available for assignment) - globally unassigned only
    admin_users = User.query.filter(User.role == 'office_admin').all()
    assigned_admin_ids_global = [oa.user_id for oa in OfficeAdmin.query.all()]
    available_admins = [user for user in admin_users if user.id not in assigned_admin_ids_global]
    
    # Log activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Viewed details for office: {office.name}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    
    return render_template('admin/office_detail.html', 
                          office=office, 
                          recent_inquiries=recent_inquiries, 
                          inquiry_stats=inquiry_stats,
                          available_admins=available_admins) 


# Edit Admin
@admin_bp.route('/office_admin/<int:admin_id>/edit/', methods=['GET', 'POST'])
@login_required
@campus_access_required
def edit_admin(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    user = office_admin.user
    # Ensure the admin belongs to the current campus via their office
    if current_user.role == 'super_admin' and office_admin.office and office_admin.office.campus_id != current_user.campus_id:
        flash('Access denied. You can only manage admins in your assigned campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    if request.method == 'POST':
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')
        user.email = request.form.get('email')
        
        # Only update password if provided
        new_password = request.form.get('password')
        if new_password and len(new_password) >= 8:
            user.password_hash = generate_password_hash(new_password)
        
        # If changing office assignment
        new_office_id = request.form.get('office_id')
        if new_office_id and int(new_office_id) != office_admin.office_id:
            # Validate new office belongs to current campus
            new_office = Office.query.get(int(new_office_id))
            if not new_office or new_office.campus_id != current_user.campus_id:
                flash('Invalid office selection for your campus.', 'error')
                return redirect(url_for('admin.edit_admin', admin_id=admin_id))
            office_admin.office_id = int(new_office_id)
        
        # Log activity
        log = SuperAdminActivityLog(
            super_admin_id=current_user.id,
            action=f"Edited admin: {user.get_full_name()}",
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        
        try:
            db.session.commit()
            flash('Admin updated successfully!', 'success')
            return redirect(url_for('admin.view_admin_details', admin_id=office_admin.id))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating the admin: {str(e)}', 'error')
    
    # Only list offices from current campus for selection
    offices = Office.query.filter(Office.campus_id == current_user.campus_id).all()
    return render_template('admin/edit_admin.html', admin=office_admin, user=user, offices=offices)

# Toggle Admin Status
@admin_bp.route('/office_admin/<int:admin_id>/toggle_status/', methods=['POST'])
@login_required
@campus_access_required
def toggle_admin_status(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    user = office_admin.user
    # Ensure the admin belongs to the current campus via their office
    if current_user.role == 'super_admin' and office_admin.office and office_admin.office.campus_id != current_user.campus_id:
        flash('Access denied. You can only manage admins in your assigned campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    # Toggle the is_active status
    user.is_active = not user.is_active
    status_text = "activated" if user.is_active else "deactivated"
    
    # Log activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"{status_text.capitalize()} admin account: {user.get_full_name()}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        flash(f'Admin account {status_text} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while updating the admin status: {str(e)}', 'error')
    
    return redirect(url_for('admin.office_stats'))

# Unassign Admin from Office
@admin_bp.route('/office_admin/<int:admin_id>/unassign/', methods=['POST'])
@login_required
@campus_access_required
def unassign_admin(admin_id):
    if current_user.role != 'super_admin':
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office_admin = OfficeAdmin.query.get_or_404(admin_id)
    # Ensure the admin belongs to the current campus via their office
    if current_user.role == 'super_admin' and office_admin.office and office_admin.office.campus_id != current_user.campus_id:
        flash('Access denied. You can only manage admins in your assigned campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    office_name = office_admin.office.name
    admin_name = office_admin.user.get_full_name()
    
    # Log activity before deletion
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Unassigned admin {admin_name} from office: {office_name}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.delete(office_admin)
        db.session.commit()
        flash(f'Admin unassigned from office successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while unassigning the admin: {str(e)}', 'error')
    
    return redirect(url_for('admin.office_stats'))

@admin_bp.route('/assign-admin', methods=['POST'])
@login_required
@campus_access_required
def assign_admin_to_office():
    if current_user.role != 'super_admin':
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office_id = request.form.get('office_id')
    admin_id = request.form.get('admin_id')
    
    if not office_id or not admin_id:
        flash('Missing required information.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office = Office.query.get(office_id)
    if not office:
        flash('Office not found.', 'error')
        return redirect(url_for('admin.office_stats'))
    # Ensure office belongs to current campus
    if current_user.role == 'super_admin' and office.campus_id != current_user.campus_id:
        flash('Access denied. You can only assign admins to offices in your campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    user = User.query.get(admin_id)
    if not user or user.role != 'office_admin':
        flash('User not found or not an admin.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    existing_assignment = OfficeAdmin.query.filter_by(user_id=admin_id, office_id=office_id).first()
    if existing_assignment:
        flash('Admin is already assigned to this office.', 'warning')
        return redirect(url_for('admin.office_stats'))
    
    new_admin = OfficeAdmin(user_id=admin_id, office_id=office_id)
    
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Assigned admin {user.get_full_name()} to office: {office.name}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.add(new_admin)
    
    try:
        db.session.commit()
        flash('Admin assigned to office successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while assigning the admin: {str(e)}', 'error')
    
    return redirect(url_for('admin.office_stats'))

@admin_bp.route('/assign-office', methods=['POST'])
@login_required
@campus_access_required
def assign_office_to_admin():
    if current_user.role != 'super_admin':
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    admin_id = request.form.get('admin_id')
    office_id = request.form.get('office_id')
    
    if not admin_id or not office_id:
        flash('Missing required information.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    user = User.query.get(admin_id)
    if not user or user.role != 'office_admin':
        flash('User not found or not an admin.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    office = Office.query.get(office_id)
    if not office:
        flash('Office not found.', 'error')
        return redirect(url_for('admin.office_stats'))
    # Ensure office belongs to current campus
    if current_user.role == 'super_admin' and office.campus_id != current_user.campus_id:
        flash('Access denied. You can only assign offices from your campus.', 'error')
        return redirect(url_for('admin.office_stats'))
    
    existing_assignment = OfficeAdmin.query.filter_by(user_id=admin_id, office_id=office_id).first()
    if existing_assignment:
        flash('Admin is already assigned to this office.', 'warning')
        return redirect(url_for('admin.office_stats'))
    
    # Create new assignment
    new_assignment = OfficeAdmin(user_id=admin_id, office_id=office_id)
    
    # Log activity
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Assigned office {office.name} to admin: {user.get_full_name()}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.add(new_assignment)
    
    try:
        db.session.commit()
        flash('Office assigned to admin successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while assigning the office: {str(e)}', 'error')
    
    return redirect(url_for('admin.office_stats'))

