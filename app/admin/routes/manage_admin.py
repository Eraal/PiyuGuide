from app.models import Inquiry, User, Office, db, OfficeAdmin, AuditLog, SuperAdminActivityLog
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func, or_, desc
from app.admin import admin_bp

@admin_bp.route('/manage-admins')
@login_required
def manage_admins():
    """
    View all admin accounts (super_admin only)
    This allows SuperAdmin to view and manage all admin accounts
    """
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get search and filter parameters
    search_query = request.args.get('search')
    office_id = request.args.get('office', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Base query for office admins with joins to users and offices
    query = db.session.query(
        User, OfficeAdmin, Office
    ).join(
        OfficeAdmin, User.id == OfficeAdmin.user_id
    ).join(
        Office, OfficeAdmin.office_id == Office.id
    ).filter(
        User.role == 'office_admin'
    )
    
    # Apply filters
    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search),
                User.last_name.ilike(search),
                User.email.ilike(search),
                Office.name.ilike(search)
            )
        )
    
    if office_id:
        query = query.filter(OfficeAdmin.office_id == office_id)
    
    if status:
        if status == 'active':
            query = query.filter(User.is_active == True, User.account_locked == False)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
        elif status == 'locked':
            query = query.filter(User.account_locked == True)
    
    # Order by created date (most recent first)
    query = query.order_by(desc(User.created_at))
    
    # Get total count for pagination
    total_count = query.count()
    
    # Apply pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    admin_results = pagination.items
    
    # Transform results for template
    admins = []
    for user, office_admin, office in admin_results:
        admins.append({
            'id': user.id,
            'office_admin_id': office_admin.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'office_id': office.id,
            'office_name': office.name,
            'is_active': user.is_active,
            'account_locked': user.account_locked,
            'created_at': user.created_at,
            'last_activity': user.last_activity
        })
    
    # Get all offices for filter dropdown
    offices = Office.query.all()
    
    # Log the action
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action="Viewed admin management page",
        target_type="system",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    
    return render_template(
        'admin/manage_admin.html',
        admins=admins,
        pagination=pagination,
        offices=offices,
        total_count=total_count,
        search_query=search_query,
        office_id=office_id,
        status=status
    )

@admin_bp.route('/admin/<int:admin_id>/details')
@login_required
def admin_details(admin_id):
    """Get detailed information about a specific admin"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    # Query admin details
    admin_data = db.session.query(
        User, OfficeAdmin, Office
    ).join(
        OfficeAdmin, User.id == OfficeAdmin.user_id
    ).join(
        Office, OfficeAdmin.office_id == Office.id
    ).filter(
        User.id == admin_id, 
        User.role == 'office_admin'
    ).first()
    
    if not admin_data:
        return jsonify({'error': 'Admin not found'}), 404
    
    user, office_admin, office = admin_data
    
    # Format the response
    admin_details = {
        'id': user.id,
        'first_name': user.first_name,
        'middle_name': user.middle_name,
        'last_name': user.last_name,
        'email': user.email,
        'office_id': office.id,
        'office_name': office.name,
        'is_active': user.is_active,
        'account_locked': user.account_locked,
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'last_activity': user.last_activity.strftime('%Y-%m-%d %H:%M:%S') if user.last_activity else None,
        'profile_pic': user.profile_pic
    }
    
    # Log the action
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Viewed admin details",
        target_type="user",
        target_user_id=admin_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify(admin_details)

@admin_bp.route('/admin/<int:admin_id>/toggle-status', methods=['POST'])
@login_required
def manage_toggle_admin_status(admin_id):
    """Toggle admin account active status"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    admin = User.query.filter_by(id=admin_id, role='office_admin').first()
    if not admin:
        return jsonify({'error': 'Admin not found'}), 404
    
    # Toggle status
    admin.is_active = not admin.is_active
    
    action = "activated" if admin.is_active else "deactivated"
    
    # Log the action
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Admin account {action}",
        target_type="user",
        target_user_id=admin_id,
        details=f"Admin account {action}: {admin.email}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Admin account {action} successfully',
            'is_active': admin.is_active
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/<int:admin_id>/toggle-lock', methods=['POST'])
@login_required
def toggle_admin_lock(admin_id):
    """Toggle admin account lock status"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    admin = User.query.filter_by(id=admin_id, role='office_admin').first()
    if not admin:
        return jsonify({'error': 'Admin not found'}), 404
    
    reason = request.json.get('reason', '')
    
    if admin.account_locked:
        # Unlock account
        admin.unlock_account(current_user, reason)
        action = "unlocked"
    else:
        # Lock account
        admin.lock_account(current_user, reason)
        action = "locked"
    
    # Log the action
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action=f"Admin account {action}",
        target_type="user",
        target_user_id=admin_id,
        details=f"Admin account {action}: {admin.email}. Reason: {reason}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Admin account {action} successfully',
            'account_locked': admin.account_locked
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/<int:admin_id>/delete', methods=['POST'])
@login_required
def delete_admin(admin_id):
    """Delete an admin account"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    admin = User.query.filter_by(id=admin_id, role='office_admin').first()
    if not admin:
        return jsonify({'error': 'Admin not found'}), 404
    
    admin_email = admin.email
    
    # Log the action before deletion
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action="Admin account deleted",
        target_type="user",
        details=f"Admin account deleted: {admin_email}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        # Delete the admin (OfficeAdmin and User records)
        office_admin = OfficeAdmin.query.filter_by(user_id=admin_id).first()
        if office_admin:
            db.session.delete(office_admin)
        
        db.session.delete(admin)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Admin account deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/<int:admin_id>/reassign', methods=['POST'])
@login_required
def reassign_admin(admin_id):
    """Reassign admin to a different office"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized access'}), 403
    
    new_office_id = request.json.get('office_id')
    if not new_office_id:
        return jsonify({'error': 'Office ID is required'}), 400
    
    # Verify the office exists
    office = Office.query.get(new_office_id)
    if not office:
        return jsonify({'error': 'Office not found'}), 404
    
    # Get the admin
    admin = User.query.filter_by(id=admin_id, role='office_admin').first()
    if not admin:
        return jsonify({'error': 'Admin not found'}), 404
    
    office_admin = OfficeAdmin.query.filter_by(user_id=admin_id).first()
    if not office_admin:
        return jsonify({'error': 'Office admin association not found'}), 404
    
    old_office_id = office_admin.office_id
    old_office = Office.query.get(old_office_id)
    
    # Update the office assignment
    office_admin.office_id = new_office_id
    
    # Log the action
    log = SuperAdminActivityLog(
        super_admin_id=current_user.id,
        action="Admin reassigned to new office",
        target_type="user",
        target_user_id=admin_id,
        target_office_id=new_office_id,
        details=f"Admin {admin.email} reassigned from {old_office.name if old_office else 'Unknown'} to {office.name}",
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Admin reassigned to {office.name} successfully',
            'office_id': new_office_id,
            'office_name': office.name
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500