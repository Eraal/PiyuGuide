from app.models import (
    Campus, User, Office, db, OfficeAdmin, SuperSuperAdminActivityLog
)
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash
from app.super_admin import super_admin_bp
from app.utils import role_required

@super_admin_bp.route('/super-admins')
@login_required
@role_required(['super_super_admin'])
def super_admin_list():
    """Display list of all super admins"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Build query with search and filtering
    search_term = request.args.get('search', '')
    campus_filter = request.args.get('campus_id', '')
    status_filter = request.args.get('status', '')
    
    query = User.query.filter_by(role='super_admin')
    
    if search_term:
        search_term = f"%{search_term}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )
    
    if campus_filter:
        if campus_filter == 'unassigned':
            query = query.filter(User.campus_id.is_(None))
        else:
            query = query.filter_by(campus_id=campus_filter)
    
    if status_filter:
        if status_filter == 'active':
            query = query.filter_by(is_active=True)
        elif status_filter == 'inactive':
            query = query.filter_by(is_active=False)
    
    # Paginate results
    super_admins = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get all campuses for filter dropdown
    campuses = Campus.query.filter_by(is_active=True).order_by(Campus.name).all()
    
    # Get statistics for each super admin
    admin_stats = {}
    for admin in super_admins.items:
        admin_stats[admin.id] = {
            'office_count': Office.query.filter_by(campus_id=admin.campus_id).count() if admin.campus_id else 0,
            'last_login': None  # You can implement last login tracking
        }
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Super Admin List",
        target_type="system",
        details=f"Viewed super admin list with filters - search: '{search_term}', campus: '{campus_filter}', status: '{status_filter}'" if any([search_term, campus_filter, status_filter]) else "Viewed super admin list",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/super_admin_list.html',
        super_admins=super_admins,
        admin_stats=admin_stats,
        campuses=campuses,
        search_term=search_term,
        campus_filter=campus_filter,
        status_filter=status_filter
    )

@super_admin_bp.route('/super-admin/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_super_admin'])
def create_super_admin():
    """Create a new super admin"""
    if request.method == 'POST':
        try:
            first_name = request.form.get('first_name')
            middle_name = request.form.get('middle_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            campus_id = request.form.get('campus_id')
            
            # Validate required fields
            if not all([first_name, last_name, email, password]):
                flash('First name, last name, email, and password are required.', 'error')
                return render_template('super_admin/create_super_admin.html', 
                                     campuses=Campus.query.filter_by(is_active=True).all())
            
            # Check if email already exists
            existing_user = User.query.filter_by(email=email.lower().strip()).first()
            if existing_user:
                flash('Email address already exists. Please choose a different email.', 'error')
                return render_template('super_admin/create_super_admin.html', 
                                     campuses=Campus.query.filter_by(is_active=True).all())
            
            # Validate password length
            if len(password) < 8:
                flash('Password must be at least 8 characters long.', 'error')
                return render_template('super_admin/create_super_admin.html', 
                                     campuses=Campus.query.filter_by(is_active=True).all())
            
            # Validate campus if provided
            campus = None
            if campus_id:
                campus = Campus.query.get(campus_id)
                if not campus or not campus.is_active:
                    flash('Invalid campus selected.', 'error')
                    return render_template('super_admin/create_super_admin.html', 
                                         campuses=Campus.query.filter_by(is_active=True).all())
            
            # Create new super admin
            new_super_admin = User(
                first_name=first_name.strip(),
                middle_name=middle_name.strip() if middle_name else None,
                last_name=last_name.strip(),
                email=email.lower().strip(),
                password_hash=generate_password_hash(password),
                role='super_admin',
                campus_id=int(campus_id) if campus_id else None,
                is_active=True
            )
            
            db.session.add(new_super_admin)
            db.session.flush()  # Get the user ID
            
            # Log this activity
            SuperSuperAdminActivityLog.log_action(
                super_super_admin=current_user,
                action="Created Super Admin",
                target_type="super_admin",
                target_user=new_super_admin,
                target_campus=campus,
                details=f"Created super admin: {new_super_admin.get_full_name()} ({new_super_admin.email})" + 
                       (f" assigned to campus: {campus.name}" if campus else " without campus assignment"),
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            
            db.session.commit()
            flash(f'Super Admin "{new_super_admin.get_full_name()}" created successfully!', 'success')
            return redirect(url_for('super_admin.super_admin_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating super admin: {str(e)}', 'error')
    
    # Get active campuses for the form
    campuses = Campus.query.filter_by(is_active=True).order_by(Campus.name).all()
    return render_template('super_admin/create_super_admin.html', campuses=campuses)

@super_admin_bp.route('/super-admin/<int:admin_id>')
@login_required
@role_required(['super_super_admin'])
def view_super_admin(admin_id):
    """View super admin details"""
    super_admin = User.query.filter_by(id=admin_id, role='super_admin').first_or_404()
    
    # Get statistics
    office_count = 0
    offices = []
    if super_admin.campus_id:
        offices = Office.query.filter_by(campus_id=super_admin.campus_id).all()
        office_count = len(offices)
    
    # Get all campuses for campus assignment modal
    campuses = Campus.query.filter_by(is_active=True).order_by(Campus.name).all()
    
    # Get recent activity logs (if you implement activity tracking for super admins)
    recent_activities = []  # You can implement this based on your logging system
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Super Admin Details",
        target_type="super_admin",
        target_user=super_admin,
        details=f"Viewed details for super admin: {super_admin.get_full_name()}",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/view_super_admin.html',
        super_admin=super_admin,
        office_count=office_count,
        offices=offices,
        recent_activities=recent_activities,
        campuses=campuses
    )

@super_admin_bp.route('/super-admin/<int:admin_id>/assign-campus', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def assign_campus(admin_id):
    """Assign or reassign a campus to a super admin"""
    try:
        super_admin = User.query.filter_by(id=admin_id, role='super_admin').first_or_404()
        campus_id = request.form.get('campus_id')
        
        old_campus = super_admin.campus
        
        if campus_id:
            campus = Campus.query.get(campus_id)
            if not campus or not campus.is_active:
                flash('Invalid campus selected.', 'error')
                return redirect(url_for('super_admin.view_super_admin', admin_id=admin_id))
            
            super_admin.campus_id = int(campus_id)
            action_details = f"Assigned super admin {super_admin.get_full_name()} to campus: {campus.name}"
            if old_campus:
                action_details = f"Reassigned super admin {super_admin.get_full_name()} from {old_campus.name} to {campus.name}"
        else:
            super_admin.campus_id = None
            action_details = f"Unassigned super admin {super_admin.get_full_name()} from campus: {old_campus.name if old_campus else 'unknown'}"
        
        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Assigned Campus to Super Admin",
            target_type="super_admin",
            target_user=super_admin,
            target_campus=super_admin.campus,
            details=action_details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        flash('Campus assignment updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating campus assignment: {str(e)}', 'error')
    
    return redirect(url_for('super_admin.view_super_admin', admin_id=admin_id))

@super_admin_bp.route('/super-admin/<int:admin_id>/toggle-status', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def toggle_super_admin_status(admin_id):
    """Toggle super admin active status"""
    try:
        super_admin = User.query.filter_by(id=admin_id, role='super_admin').first_or_404()
        old_status = super_admin.is_active
        super_admin.is_active = not super_admin.is_active
        
        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Toggled Super Admin Status",
            target_type="super_admin",
            target_user=super_admin,
            details=f"Super admin '{super_admin.get_full_name()}' status changed from {'active' if old_status else 'inactive'} to {'active' if super_admin.is_active else 'inactive'}",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        status_text = 'activated' if super_admin.is_active else 'deactivated'
        flash(f'Super Admin "{super_admin.get_full_name()}" has been {status_text}.', 'success')
        
        return jsonify({'success': True, 'is_active': super_admin.is_active})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@super_admin_bp.route('/office-admin/<int:admin_id>/toggle-status', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def toggle_office_admin_status(admin_id):
    """Toggle office admin active status"""
    try:
        office_admin_user = User.query.filter_by(id=admin_id, role='office_admin').first_or_404()
        old_status = office_admin_user.is_active
        office_admin_user.is_active = not office_admin_user.is_active
        
        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Toggled Office Admin Status",
            target_type="office_admin",
            target_user=office_admin_user,
            details=f"Office admin '{office_admin_user.get_full_name()}' status changed from {'active' if old_status else 'inactive'} to {'active' if office_admin_user.is_active else 'inactive'}",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        status_text = 'activated' if office_admin_user.is_active else 'deactivated'
        flash(f'Office Admin "{office_admin_user.get_full_name()}" has been {status_text}.', 'success')
        
        return jsonify({'success': True, 'is_active': office_admin_user.is_active})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@super_admin_bp.route('/super-admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['super_super_admin'])
def edit_super_admin(admin_id):
    """Edit super admin details"""
    super_admin = User.query.filter_by(id=admin_id, role='super_admin').first_or_404()
    
    if request.method == 'POST':
        try:
            first_name = request.form.get('first_name')
            middle_name = request.form.get('middle_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            campus_id = request.form.get('campus_id')
            is_active = 'is_active' in request.form
            
            # Validate required fields
            if not all([first_name, last_name, email]):
                flash('First name, last name, and email are required.', 'error')
                return render_template('super_admin/edit_super_admin.html', 
                                     super_admin=super_admin,
                                     available_campuses=Campus.query.filter_by(is_active=True).all())
            
            # Check if email already exists for another user
            existing_user = User.query.filter(User.email == email.lower().strip(), User.id != admin_id).first()
            if existing_user:
                flash('Email address already exists. Please choose a different email.', 'error')
                return render_template('super_admin/edit_super_admin.html', 
                                     super_admin=super_admin,
                                     available_campuses=Campus.query.filter_by(is_active=True).all())
            
            # Validate password if provided
            if password and len(password) < 8:
                flash('Password must be at least 8 characters long.', 'error')
                return render_template('super_admin/edit_super_admin.html', 
                                     super_admin=super_admin,
                                     available_campuses=Campus.query.filter_by(is_active=True).all())
            
            # Validate campus if provided
            campus = None
            if campus_id:
                campus = Campus.query.get(campus_id)
                if not campus or not campus.is_active:
                    flash('Invalid campus selected.', 'error')
                    return render_template('super_admin/edit_super_admin.html', 
                                         super_admin=super_admin,
                                         available_campuses=Campus.query.filter_by(is_active=True).all())
            
            # Store old values for logging
            old_values = {
                'first_name': super_admin.first_name,
                'middle_name': super_admin.middle_name,
                'last_name': super_admin.last_name,
                'email': super_admin.email,
                'campus_id': super_admin.campus_id,
                'is_active': super_admin.is_active
            }
            
            # Update super admin details
            super_admin.first_name = first_name.strip()
            super_admin.middle_name = middle_name.strip() if middle_name else None
            super_admin.last_name = last_name.strip()
            super_admin.email = email.lower().strip()
            super_admin.campus_id = int(campus_id) if campus_id else None
            super_admin.is_active = is_active
            
            # Update password if provided
            if password:
                super_admin.password_hash = generate_password_hash(password)
            
            # Handle profile picture upload
            if 'profile_pic' in request.files and request.files['profile_pic'].filename:
                # Add profile picture handling logic here if needed
                pass
            
            # Build change details for logging
            changes = []
            if old_values['first_name'] != super_admin.first_name:
                changes.append(f"First name: {old_values['first_name']} → {super_admin.first_name}")
            if old_values['middle_name'] != super_admin.middle_name:
                changes.append(f"Middle name: {old_values['middle_name'] or 'None'} → {super_admin.middle_name or 'None'}")
            if old_values['last_name'] != super_admin.last_name:
                changes.append(f"Last name: {old_values['last_name']} → {super_admin.last_name}")
            if old_values['email'] != super_admin.email:
                changes.append(f"Email: {old_values['email']} → {super_admin.email}")
            if old_values['campus_id'] != super_admin.campus_id:
                old_campus = Campus.query.get(old_values['campus_id']).name if old_values['campus_id'] else 'None'
                new_campus = campus.name if campus else 'None'
                changes.append(f"Campus: {old_campus} → {new_campus}")
            if old_values['is_active'] != super_admin.is_active:
                changes.append(f"Status: {'Active' if old_values['is_active'] else 'Inactive'} → {'Active' if super_admin.is_active else 'Inactive'}")
            if password:
                changes.append("Password updated")
            
            # Log this activity
            SuperSuperAdminActivityLog.log_action(
                super_super_admin=current_user,
                action="Updated Super Admin",
                target_type="super_admin",
                target_user=super_admin,
                target_campus=campus,
                details=f"Updated super admin: {super_admin.get_full_name()}. Changes: {', '.join(changes) if changes else 'No changes made'}",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            
            db.session.commit()
            flash(f'Super Admin "{super_admin.get_full_name()}" updated successfully!', 'success')
            return redirect(url_for('super_admin.view_super_admin', admin_id=admin_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating super admin: {str(e)}', 'error')
    
    # Get available campuses for the form
    available_campuses = Campus.query.filter_by(is_active=True).order_by(Campus.name).all()
    
    return render_template('super_admin/edit_super_admin.html', 
                         super_admin=super_admin,
                         available_campuses=available_campuses)

@super_admin_bp.route('/all-admins')
@login_required
@role_required(['super_super_admin'])
def all_admins_list():
    """Display list of all administrators (both office admins and super admins)"""
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    # Build query with search and filtering
    search_term = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    campus_filter = request.args.get('campus_id', '')
    status_filter = request.args.get('status', '')
    
    # Base query for both office_admin and super_admin roles
    query = User.query.filter(User.role.in_(['office_admin', 'super_admin']))
    
    if search_term:
        search_term = f"%{search_term}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )
    
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    if campus_filter:
        if campus_filter == 'unassigned':
            query = query.filter(User.campus_id.is_(None))
        else:
            query = query.filter_by(campus_id=campus_filter)
    
    if status_filter:
        if status_filter == 'active':
            query = query.filter_by(is_active=True)
        elif status_filter == 'inactive':
            query = query.filter_by(is_active=False)
    
    # Paginate results
    all_admins = query.order_by(User.role, User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get all campuses for filter dropdown
    campuses = Campus.query.filter_by(is_active=True).order_by(Campus.name).all()
    
    # Get statistics for each admin
    admin_stats = {}
    for admin in all_admins.items:
        admin_stats[admin.id] = {
            'office_count': 0,
            'assigned_office': None,
            'last_login': None
        }
        
        if admin.role == 'super_admin':
            # Count offices in their campus
            admin_stats[admin.id]['office_count'] = Office.query.filter_by(campus_id=admin.campus_id).count() if admin.campus_id else 0
        elif admin.role == 'office_admin':
            # Get their assigned office
            if admin.office_admin:
                admin_stats[admin.id]['assigned_office'] = admin.office_admin.office
                admin_stats[admin.id]['office_count'] = 1
    
    # Calculate summary statistics
    total_admins = all_admins.total
    super_admin_count = User.query.filter_by(role='super_admin').count()
    office_admin_count = User.query.filter_by(role='office_admin').count()
    active_admins = User.query.filter(User.role.in_(['office_admin', 'super_admin']), User.is_active == True).count()
    inactive_admins = total_admins - active_admins
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed All Admins List",
        target_type="system",
        details=f"Viewed all admins list with filters - search: '{search_term}', role: '{role_filter}', campus: '{campus_filter}', status: '{status_filter}'" if any([search_term, role_filter, campus_filter, status_filter]) else "Viewed all admins list",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/all_admins_list.html',
        all_admins=all_admins,
        admin_stats=admin_stats,
        campuses=campuses,
        search_term=search_term,
        role_filter=role_filter,
        campus_filter=campus_filter,
        status_filter=status_filter,
        total_admins=total_admins,
        super_admin_count=super_admin_count,
        office_admin_count=office_admin_count,
        active_admins=active_admins,
        inactive_admins=inactive_admins
    )
