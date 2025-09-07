from app.models import (
    Campus, User, SuperSuperAdminActivityLog, SuperAdminActivityLog, SystemSettings, db
)
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app.super_admin import super_admin_bp
from app.utils import role_required
from werkzeug.utils import secure_filename
import os
from sqlalchemy import or_

@super_admin_bp.route('/settings')
@login_required
@role_required(['super_super_admin'])
def settings():
    """Super Super Admin settings and account management"""
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Settings",
        target_type="system",
        details="Accessed Super Super Admin settings page",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    # Current branding
    brand_title = SystemSettings.get_brand_title()
    brand_logo_path = SystemSettings.get_brand_logo_path()
    return render_template('super_admin/settings.html', brand_title=brand_title, brand_logo_path=brand_logo_path)

@super_admin_bp.route('/profile')
@login_required
@role_required(['super_super_admin'])
def profile():
    """Super Super Admin profile page (read-only overview)."""
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Profile",
        target_type="account",
        details="Accessed Super Super Admin profile page",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )

    # Optional: derive campus info for display
    campus = None
    try:
        if getattr(current_user, 'campus_id', None):
            campus = Campus.query.get(current_user.campus_id)
    except Exception:
        campus = None

    return render_template('super_admin/profile.html', campus=campus)

@super_admin_bp.route('/account-settings')
@login_required
@role_required(['super_super_admin'])
def account_settings():
    """Dedicated page to update super super admin profile and password."""
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Account Settings",
        target_type="account",
        details="Accessed Account Settings page",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    return render_template('super_admin/account_settings.html')

@super_admin_bp.route('/profile/picture/update', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def update_profile_picture():
    """Upload and update the current user's profile picture.

    Stores under static/uploads/profile_pics and saves a circle-cropped PNG.
    """
    try:
        file = request.files.get('profile_pic')
        if not file or not file.filename:
            flash('Please choose an image to upload.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        allowed = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
        if ext not in allowed:
            flash('Unsupported image type. Use PNG, JPG, JPEG, GIF, or WEBP.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        # Resolve upload directory
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        if not upload_root:
            project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
            upload_root = os.path.join(project_root, 'static', 'uploads')
        profile_dir = os.path.join(upload_root, 'profile_pics')
        os.makedirs(profile_dir, exist_ok=True)

        import time
        # Save processed avatars as PNG to preserve quality/transparency
        out_name = f"avatar_{current_user.id}_{int(time.time())}.png"
        full_path = os.path.join(profile_dir, out_name)

        # Process: circle-crop; background removal is unnecessary for avatars
        try:
            from app.utils.image_tools import circle_crop
            from PIL import Image
            img = Image.open(file.stream)
            img = circle_crop(img, padding=2)
            # Resize to a sensible max size (e.g., 512x512)
            max_size = 512
            if img.width > max_size or img.height > max_size:
                img = img.resize((max_size, max_size))
            img.save(full_path, format='PNG')
        except Exception:
            # Fallback to raw save
            file.save(full_path)

        # Normalize path to static-relative
        rel_path = os.path.join('uploads', 'profile_pics', out_name).replace('\\', '/')
        old_path = current_user.profile_pic
        current_user.profile_pic = rel_path

        # Log activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Updated Profile Picture",
            target_type="account",
            details=f"Changed profile picture{f' from {old_path}' if old_path else ''}",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )

        db.session.commit()
        flash('Profile picture updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile picture: {str(e)}', 'error')

    return redirect(url_for('super_admin.account_settings'))

@super_admin_bp.route('/profile/picture/remove', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def remove_profile_picture():
    """Remove current user's profile picture reference (does not delete file)."""
    try:
        had_pic = bool(current_user.profile_pic)
        current_user.profile_pic = None

        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Removed Profile Picture",
            target_type="account",
            details="Cleared profile picture",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )

        db.session.commit()
        flash('Profile picture removed.' if had_pic else 'No profile picture to remove.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing profile picture: {str(e)}', 'error')

    return redirect(url_for('super_admin.account_settings'))

@super_admin_bp.route('/branding/update', methods=['POST'], endpoint='update_branding')
@login_required
@role_required(['super_super_admin'])
def update_branding():
    """Update system branding (title and logo)"""
    try:
        new_title = (request.form.get('brand_title') or '').strip()
        new_tagline = (request.form.get('brand_tagline') or '').strip()
        default_campus_name = (request.form.get('current_campus_name') or '').strip()
        logo_url = (request.form.get('brand_logo_url') or '').strip()
        logo_file = request.files.get('brand_logo_file')
        favicon_file = request.files.get('favicon_file')

        # Update simple text settings
        if new_title:
            SystemSettings.set_brand_title(new_title, updated_by=current_user)
        if new_tagline:
            SystemSettings.set_brand_tagline(new_tagline, updated_by=current_user)
        if default_campus_name:
            SystemSettings.set_current_campus_name(default_campus_name, updated_by=current_user)

        # Handle logo upload or URL
        if logo_file and logo_file.filename:
            filename = secure_filename(logo_file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                flash('Logo must be an image file (png, jpg, jpeg, gif, webp).', 'error')
                return redirect(url_for('super_admin.settings'))

            upload_root = current_app.config.get('UPLOAD_FOLDER')
            if not upload_root:
                project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
                upload_root = os.path.join(project_root, 'static', 'uploads')
            branding_dir = os.path.join(upload_root, 'branding')
            os.makedirs(branding_dir, exist_ok=True)

            import time
            # Always save processed logos as PNG to preserve transparency
            filename = f"brand_{int(time.time())}.png"
            full_path = os.path.join(branding_dir, filename)

            # Process: remove white/solid background and circle-crop
            try:
                from app.utils.image_tools import process_logo_image
                processed = process_logo_image(logo_file, remove_bg=False, circle=True)
                processed.save(full_path, format='PNG')
            except Exception:
                # Fallback to raw save if processing fails
                logo_file.save(full_path)

            saved_logo_path = os.path.join('uploads', 'branding', filename).replace('\\', '/')
            SystemSettings.set_brand_logo_path(saved_logo_path, updated_by=current_user)
        elif logo_url:
            SystemSettings.set_brand_logo_path(logo_url, updated_by=current_user)

        # Handle favicon upload
        if favicon_file and favicon_file.filename:
            filename_fav = secure_filename(favicon_file.filename)
            ext_fav = os.path.splitext(filename_fav)[1].lower()
            if ext_fav not in ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp']:
                flash('Favicon must be an image file (png, jpg, jpeg, gif, ico, webp).', 'error')
                return redirect(url_for('super_admin.settings'))

            upload_root = current_app.config.get('UPLOAD_FOLDER')
            if not upload_root:
                project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
                upload_root = os.path.join(project_root, 'static', 'uploads')
            branding_dir = os.path.join(upload_root, 'branding')
            os.makedirs(branding_dir, exist_ok=True)

            import time
            filename_fav = f"favicon_{int(time.time())}{ext_fav}"
            full_path_fav = os.path.join(branding_dir, filename_fav)
            favicon_file.save(full_path_fav)

            fav_rel = os.path.join('uploads', 'branding', filename_fav).replace('\\', '/')
            SystemSettings.set_favicon_path(fav_rel, updated_by=current_user)

        # Log activity
        changed = []
        if new_title:
            changed.append('title')
        if new_tagline:
            changed.append('tagline')
        if default_campus_name:
            changed.append('default_campus_name')
        if logo_file and logo_file.filename:
            changed.append('logo_file')
        elif logo_url:
            changed.append('logo_url')
        if favicon_file and favicon_file.filename:
            changed.append('favicon')

        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Updated Branding",
            target_type="system",
            details=f"Updated branding fields: {', '.join(changed) if changed else 'none'}",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        db.session.commit()
        flash('Branding updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating branding: {str(e)}', 'error')

    return redirect(url_for('super_admin.settings'))

@super_admin_bp.route('/profile/update', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def update_profile():
    """Update super super admin profile"""
    try:
        old_email = current_user.email

        current_user.first_name = (request.form.get('first_name') or '').strip()
        current_user.middle_name = (request.form.get('middle_name') or '').strip() or None
        current_user.last_name = (request.form.get('last_name') or '').strip()

        new_email = (request.form.get('email') or '').lower().strip()

        # Validate required fields
        if not all([current_user.first_name, current_user.last_name, new_email]):
            flash('First name, last name, and email are required.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        # Check if email is being changed and if it already exists
        if new_email != old_email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user:
                flash('Email address already exists. Please choose a different email.', 'error')
                return redirect(url_for('super_admin.account_settings'))
            current_user.email = new_email

        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Updated Profile",
            target_type="account",
            details=(
                "Updated profile information"
                + (f", email changed from {old_email} to {new_email}" if old_email != new_email else "")
            ),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )

        # Commit changes
        db.session.commit()
        flash('Profile updated successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')

    return redirect(url_for('super_admin.account_settings'))

@super_admin_bp.route('/password/change', methods=['POST'])
@login_required
@role_required(['super_super_admin'])
def change_password():
    """Change super super admin password"""
    try:
        current_password = (request.form.get('current_password') or '')
        new_password = (request.form.get('new_password') or '')
        confirm_password = (request.form.get('confirm_password') or '')

        # Validate current password
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        # Validate new password
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        # Validate password confirmation
        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return redirect(url_for('super_admin.account_settings'))

        # Update password
        current_user.password_hash = generate_password_hash(new_password)

        # Log this activity
        SuperSuperAdminActivityLog.log_action(
            super_super_admin=current_user,
            action="Changed Password",
            target_type="account",
            details="Password changed successfully",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )

        # Commit changes
        db.session.commit()
        flash('Password changed successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error changing password: {str(e)}', 'error')

    return redirect(url_for('super_admin.account_settings'))

@super_admin_bp.route('/activity-logs')
@login_required
@role_required(['super_super_admin'])
def activity_logs():
    """View activity logs exclusively for Super Admin (campus admin) actions"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Build query with search and filtering
    search_term = request.args.get('search', '').strip()
    action_filter = request.args.get('action', '').strip()
    target_filter = request.args.get('target', '').strip()
    status_filter = request.args.get('status', '').strip()  # 'success' | 'failed' | ''
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Join with User to allow searching by admin name/email
    query = db.session.query(SuperAdminActivityLog, User).outerjoin(
        User, SuperAdminActivityLog.super_admin_id == User.id
    )

    if search_term:
        like = f"%{search_term}%"
        query = query.filter(
            or_(
                SuperAdminActivityLog.details.ilike(like),
                SuperAdminActivityLog.action.ilike(like),
                SuperAdminActivityLog.target_type.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.email.ilike(like)
            )
        )

    if action_filter:
        query = query.filter(SuperAdminActivityLog.action == action_filter)

    if target_filter:
        query = query.filter(SuperAdminActivityLog.target_type == target_filter)

    if status_filter:
        if status_filter == 'success':
            query = query.filter(SuperAdminActivityLog.is_success.is_(True))
        elif status_filter == 'failed':
            query = query.filter(SuperAdminActivityLog.is_success.is_(False))

    if date_from:
        query = query.filter(SuperAdminActivityLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))

    if date_to:
        query = query.filter(SuperAdminActivityLog.timestamp <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))

    # Paginate results (order by newest first)
    logs = query.order_by(SuperAdminActivityLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Distinct lists for filters
    unique_actions = [row[0] for row in db.session.query(SuperAdminActivityLog.action).distinct().all()]
    unique_targets = [row[0] for row in db.session.query(SuperAdminActivityLog.target_type).distinct().all() if row[0]]

    # Log that super super admin viewed the page
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Super Admin Activity Logs",
        target_type="system",
        details=(
            f"Filters - search: '{search_term}', action: '{action_filter}', target: '{target_filter}', status: '{status_filter}', date_from: '{date_from}', date_to: '{date_to}'"
            if any([search_term, action_filter, target_filter, status_filter, date_from, date_to])
            else "Viewed without filters"
        ),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )

    return render_template(
        'super_admin/activity_logs.html',
        logs=logs,
        unique_actions=unique_actions,
        unique_targets=unique_targets,
        search_term=search_term,
        action_filter=action_filter,
        target_filter=target_filter,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to
    )
