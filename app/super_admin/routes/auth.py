from flask import render_template, redirect, url_for, flash, request
from werkzeug.security import check_password_hash
from flask_login import login_user, login_required, current_user
from flask import jsonify
from app.models import User, AuditLog, SuperSuperAdminActivityLog
from datetime import datetime
from app.extensions import db
from app.super_admin import super_admin_bp
from app.utils.decorators import role_required

@super_admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Super Super Admin login page"""
    # If user is already logged in and is super_super_admin, redirect to dashboard
    if current_user.is_authenticated and current_user.role == 'super_super_admin':
        return redirect(url_for('super_admin.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('super_admin/login.html')
        
        # Find user with super_super_admin role
        user = User.query.filter_by(email=email, role='super_super_admin').first()
        
        if user and check_password_hash(user.password_hash, password):
            # Check if account is active and not locked
            if not user.can_login():
                if user.account_locked:
                    flash('Your account has been locked. Please contact system administrator.', 'error')
                else:
                    flash('Your account is inactive. Please contact system administrator.', 'error')
                return render_template('super_admin/login.html')
            
            # Update online status and last activity time
            user.is_online = True
            user.last_activity = datetime.utcnow()
            
            # Successful login
            login_user(user)
            flash('Welcome to the System Administration Portal!', 'success')

            # Log successful login
            log = AuditLog(
                actor_id=user.id,
                actor_role=user.role,
                action='Super Super Admin Login',
                target_type='authentication',
                status_snapshot='success',
                is_success=True,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None
            )
            db.session.add(log)
            
            # Log in super super admin activity log
            SuperSuperAdminActivityLog.log_action(
                super_super_admin=user,
                action="Logged In",
                target_type="system",
                details="Successful login to System Administration Portal",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            
            db.session.commit()
            
            return redirect(url_for('super_admin.dashboard'))
        else:
            # Failed login attempt
            log = AuditLog(
                actor_id=user.id if user else None,
                actor_role='super_super_admin' if user else None,
                action='Failed Super Super Admin Login',
                target_type='authentication',
                status_snapshot='failed',
                is_success=False,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason='Invalid credentials'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('Invalid email or password. Access denied.', 'error')
            return render_template('super_admin/login.html')
    
    return render_template('super_admin/login.html')


@super_admin_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def mark_all_notifications_read():
    """Mark all notifications for current user as read."""
    try:
        from app.models import Notification
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        from app.extensions import db as _db
        _db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
