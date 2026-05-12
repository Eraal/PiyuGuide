from app.models import (
    Campus, User, Office, db, OfficeAdmin, SuperSuperAdminActivityLog, Inquiry
)
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func, or_, desc
from app.super_admin import super_admin_bp
from app.utils import role_required
from werkzeug.utils import secure_filename
import os
import time

# Allowed branding assets and theme options
ALLOWED_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
THEME_KEYS = ['blue', 'emerald', 'violet', 'sunset', 'teal', 'indigo']

@super_admin_bp.route('/campuses')
@login_required
@role_required(['super_super_admin'])
def campus_list():
    """Display list of all campuses"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Build query with search
    search_term = request.args.get('search', '')
    query = Campus.query
    
    if search_term:
        search_term = f"%{search_term}%"
        query = query.filter(
            or_(
                Campus.name.ilike(search_term),
                Campus.code.ilike(search_term),
                Campus.address.ilike(search_term)
            )
        )
    
    # Sort: Active campuses first, then by newest created
    query = query.order_by(desc(Campus.is_active), desc(Campus.created_at))

    # Paginate results
    campuses = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get campus statistics
    campus_stats = {}
    for campus in campuses.items:
        campus_stats[campus.id] = {
            'super_admin_count': User.query.filter_by(campus_id=campus.id, role='super_admin', is_active=True).count(),
            'office_count': Office.query.filter_by(campus_id=campus.id).count(),
            'active_office_admin_count': db.session.query(func.count(OfficeAdmin.id)).join(Office).filter(Office.campus_id == campus.id).scalar()
        }
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Campus List",
        target_type="system",
        details=f"Viewed campus list with search: '{search_term}'" if search_term else "Viewed campus list",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/campus_list.html',
        campuses=campuses,
        campus_stats=campus_stats,
        search_term=search_term
    )

@super_admin_bp.route('/campus/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_super_admin'])
def create_campus():
    """Create a new campus"""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            code = request.form.get('code')
            address = request.form.get('address')
            description = request.form.get('description')
            theme_key = (request.form.get('campus_theme_key') or 'blue').strip().lower()
            # Optional URLs (if user prefers URLs over uploads)
            logo_url = (request.form.get('campus_logo_url') or '').strip()
            bg_url = (request.form.get('campus_bg_url') or '').strip()
            # Optional files
            logo_file = request.files.get('campus_logo_file')
            bg_file = request.files.get('campus_bg_file')
            
            # Validate required fields
            if not name or not code:
                flash('Campus name and code are required.', 'error')
                return render_template('super_admin/create_campus.html')
            
            # Check if code already exists
            existing_campus = Campus.query.filter_by(code=code.upper()).first()
            if existing_campus:
                flash('Campus code already exists. Please choose a different code.', 'error')
                return render_template('super_admin/create_campus.html')
            
            # Create new campus
            new_campus = Campus(
                name=name.strip(),
                code=code.upper().strip(),
                address=address.strip() if address else None,
                description=description.strip() if description else None,
                campus_theme_key=theme_key if theme_key in THEME_KEYS else 'blue',
                is_active=True
            )
            
            db.session.add(new_campus)
            db.session.flush()  # Get the campus ID
            
            # Handle branding uploads/URLs now that we have campus ID
            try:
                # Resolve upload root
                upload_root = current_app.config.get('UPLOAD_FOLDER')
                if not upload_root:
                    project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
                    upload_root = os.path.join(project_root, 'static', 'uploads')
                branding_dir = os.path.join(upload_root, 'branding')
                os.makedirs(branding_dir, exist_ok=True)

                # Logo upload takes precedence over URL
                if logo_file and getattr(logo_file, 'filename', ''):
                    filename = secure_filename(logo_file.filename)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in ALLOWED_IMAGE_EXTS:
                        flash('Logo must be an image (png, jpg, jpeg, gif, webp).', 'error')
                        return render_template('super_admin/create_campus.html')
                    safe_name = f"campus_{new_campus.id}_logo_{int(time.time())}.png"
                    full_path = os.path.join(branding_dir, safe_name)
                    # Process logo (circle crop, keep transparency)
                    try:
                        from app.utils.image_tools import process_logo_image
                        processed = process_logo_image(logo_file, remove_bg=False, circle=True)
                        processed.save(full_path, format='PNG')
                    except Exception:
                        logo_file.save(full_path)
                    rel_path = os.path.join('uploads', 'branding', safe_name).replace('\\', '/')
                    new_campus.campus_logo_path = rel_path
                elif logo_url:
                    new_campus.campus_logo_path = logo_url

                # Background upload takes precedence over URL
                if bg_file and getattr(bg_file, 'filename', ''):
                    filename = secure_filename(bg_file.filename)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in ALLOWED_IMAGE_EXTS:
                        flash('Background must be an image (png, jpg, jpeg, gif, webp).', 'error')
                        return render_template('super_admin/create_campus.html')
                    safe_name = f"campus_{new_campus.id}_bg_{int(time.time())}{ext}"
                    full_path = os.path.join(branding_dir, safe_name)
                    bg_file.save(full_path)
                    rel_path = os.path.join('uploads', 'branding', safe_name).replace('\\', '/')
                    new_campus.campus_landing_bg_path = rel_path
                elif bg_url:
                    new_campus.campus_landing_bg_path = bg_url
            except Exception as asset_err:
                # Non-fatal; allow campus creation but warn
                flash(f'Campus created but branding assets failed: {asset_err}', 'warning')
            
            # Log this activity
            SuperSuperAdminActivityLog.log_action(
                super_super_admin=current_user,
                action="Created Campus",
                target_type="campus",
                target_campus=new_campus,
                details=f"Created campus: {new_campus.name} ({new_campus.code})",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            
            db.session.commit()
            flash(f'Campus "{new_campus.name}" created successfully!', 'success')
            return redirect(url_for('super_admin.campus_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating campus: {str(e)}', 'error')
    
    return render_template('super_admin/create_campus.html')

@super_admin_bp.route('/campus/<int:campus_id>')
@login_required
@role_required(['super_super_admin'])
def view_campus(campus_id):
    """View campus details"""
    campus = Campus.query.get_or_404(campus_id)
    
    # Get campus statistics
    super_admins = User.query.filter_by(campus_id=campus_id, role='super_admin', is_active=True).all()
    offices = Office.query.filter_by(campus_id=campus_id).all()
    
    # Get office admin counts + details for each office
    office_stats = {}
    office_admins_map = {}
    office_concerns_map = {}
    for office in offices:
        admins = OfficeAdmin.query.filter_by(office_id=office.id).all()
        office_stats[office.id] = {
            'admin_count': len(admins),
            'inquiry_count': Inquiry.query.filter_by(office_id=office.id).count()
        }
        office_admins_map[office.id] = [
            (admin.user.get_full_name() if hasattr(admin.user, 'get_full_name') and admin.user.get_full_name() else admin.user.email)
            for admin in admins if admin.user
        ]
        # Supported concerns names
        try:
            office_concerns_map[office.id] = [ct.concern_type.name for ct in office.supported_concerns if ct.concern_type]
        except Exception:
            office_concerns_map[office.id] = []
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Campus Details",
        target_type="campus",
        target_campus=campus,
        details=f"Viewed details for campus: {campus.name}",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/view_campus.html',
        campus=campus,
        super_admins=super_admins,
        offices=offices,
        office_stats=office_stats,
        office_admins_map=office_admins_map,
        office_concerns_map=office_concerns_map
    )

@super_admin_bp.route('/campus/<int:campus_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['super_super_admin'])
def edit_campus(campus_id):
    """Edit campus details"""
    campus = Campus.query.get_or_404(campus_id)
    
    if request.method == 'POST':
        try:
            old_name = campus.name
            old_code = campus.code
            
            campus.name = request.form.get('name').strip()
            campus.code = request.form.get('code').upper().strip()
            campus.address = request.form.get('address').strip() if request.form.get('address') else None
            campus.description = request.form.get('description').strip() if request.form.get('description') else None
            campus.is_active = request.form.get('is_active') == 'on'
            
            # Validate required fields
            if not campus.name or not campus.code:
                flash('Campus name and code are required.', 'error')
                return render_template('super_admin/edit_campus.html', campus=campus)
            
            # Check if code already exists (excluding current campus)
            existing_campus = Campus.query.filter(Campus.code == campus.code, Campus.id != campus_id).first()
            if existing_campus:
                flash('Campus code already exists. Please choose a different code.', 'error')
                return render_template('super_admin/edit_campus.html', campus=campus)
            
            # Log this activity
            changes = []
            if old_name != campus.name:
                changes.append(f"name: '{old_name}' → '{campus.name}'")
            if old_code != campus.code:
                changes.append(f"code: '{old_code}' → '{campus.code}'")
            
            SuperSuperAdminActivityLog.log_action(
                super_super_admin=current_user,
                action="Updated Campus",
                target_type="campus",
                target_campus=campus,
                details=f"Updated campus: {', '.join(changes) if changes else 'minor details updated'}",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            
            db.session.commit()
            flash(f'Campus "{campus.name}" updated successfully!', 'success')
            return redirect(url_for('super_admin.view_campus', campus_id=campus.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating campus: {str(e)}', 'error')
    
    return render_template('super_admin/edit_campus.html', campus=campus)

@super_admin_bp.route('/campus/<int:campus_id>/toggle-status', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def toggle_campus_status(campus_id):
    """Toggle campus active status"""
    try:
        campus = Campus.query.get_or_404(campus_id)
        old_status = campus.is_active
        campus.is_active = not campus.is_active
        
        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Toggled Campus Status",
            target_type="campus",
            target_campus=campus,
            details=f"Campus '{campus.name}' status changed from {'active' if old_status else 'inactive'} to {'active' if campus.is_active else 'inactive'}",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        status_text = 'activated' if campus.is_active else 'deactivated'
        flash(f'Campus "{campus.name}" has been {status_text}.', 'success')
        
        return jsonify({'success': True, 'is_active': campus.is_active})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@super_admin_bp.route('/campus/<int:campus_id>/set-default', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def set_default_campus(campus_id):
    """Set a campus as the default campus name"""
    try:
        campus = Campus.query.get_or_404(campus_id)
        
        # Import SystemSettings from models
        from app.models import SystemSettings
        
        # Set this campus as the default
        SystemSettings.set_current_campus_name(
            campus.name, 
            updated_by=current_user
        )
        
        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action=f"Set Default Campus",
            target_type="campus",
            target_id=campus.id,
            details=f"Set '{campus.name}' as the default campus name",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        flash(f'"{campus.name}" has been set as the default campus.', 'success')
        return jsonify({'success': True, 'campus_name': campus.name})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
