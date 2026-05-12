from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import time

from app.admin import admin_bp
from app.models import Campus, db, User, Notification
from app.websockets.dashboard import broadcast_campus_name_update
from app.utils.decorators import role_required, campus_access_required

ALLOWED_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
THEME_KEYS = ['blue', 'emerald', 'violet', 'sunset', 'teal', 'indigo']


@admin_bp.route('/system-customization', methods=['GET'])
@login_required
@role_required(['super_admin'])
@campus_access_required
def system_customization():
	"""Campus Admin page to customize campus-specific branding and theme."""
	campus = None
	if getattr(current_user, 'campus_id', None):
		campus = Campus.query.get(current_user.campus_id)
	return render_template('admin/system_customization.html', campus=campus, theme_keys=THEME_KEYS)


@admin_bp.route('/system-customization', methods=['POST'])
@login_required
@role_required(['super_admin'])
@campus_access_required
def update_system_customization():
	"""Handle updates for campus-specific branding and theme."""
	try:
		if not current_user.campus_id:
			flash('Your account is not assigned to any campus.', 'error')
			return redirect(url_for('admin.system_customization'))

		campus = Campus.query.get_or_404(current_user.campus_id)
		old_name_snapshot = campus.name

		# Gather inputs
		# Campus details
		name_input = (request.form.get('campus_name') or '').strip()
		code_input = (request.form.get('campus_code') or '').strip().upper()
		address_input = (request.form.get('campus_address') or '').strip()
		description_input = (request.form.get('campus_description') or '').strip()

		# Validate and update campus basic details
		if name_input:
			campus.name = name_input

		if code_input:
			if code_input != campus.code:
				# Ensure new code is unique
				existing = Campus.query.filter(Campus.code == code_input, Campus.id != campus.id).first()
				if existing:
					flash('Campus code already in use by another campus.', 'error')
					return redirect(url_for('admin.system_customization'))
			campus.code = code_input

		# Optional fields
		campus.address = address_input or None
		campus.description = description_input or None

		theme_key = (request.form.get('campus_theme_key') or '').strip().lower()
		logo_url = (request.form.get('campus_logo_url') or '').strip()
		bg_url = (request.form.get('campus_bg_url') or '').strip()
		logo_file = request.files.get('campus_logo_file')
		bg_file = request.files.get('campus_bg_file')

		# Validate theme key
		if theme_key and theme_key in THEME_KEYS:
			campus.campus_theme_key = theme_key

		# Resolve upload root
		upload_root = current_app.config.get('UPLOAD_FOLDER')
		if not upload_root:
			project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
			upload_root = os.path.join(project_root, 'static', 'uploads')
		branding_dir = os.path.join(upload_root, 'branding')
		os.makedirs(branding_dir, exist_ok=True)

		# Handle logo upload
		if logo_file and logo_file.filename:
			filename = secure_filename(logo_file.filename)
			ext = os.path.splitext(filename)[1].lower()
			if ext not in ALLOWED_IMAGE_EXTS:
				flash('Logo must be an image (png, jpg, jpeg, gif, webp).', 'error')
				return redirect(url_for('admin.system_customization'))

			# Always save processed logos as PNG to preserve transparency
			safe_name = f"campus_{campus.id}_logo_{int(time.time())}.png"
			full_path = os.path.join(branding_dir, safe_name)

			# Process: remove background and circle-crop
			try:
				from app.utils.image_tools import process_logo_image
				processed = process_logo_image(logo_file, remove_bg=False, circle=True)
				processed.save(full_path, format='PNG')
			except Exception:
				logo_file.save(full_path)

			rel_path = os.path.join('uploads', 'branding', safe_name).replace('\\', '/')
			campus.campus_logo_path = rel_path
		elif logo_url:
			campus.campus_logo_path = logo_url

		# Handle background upload
		if bg_file and bg_file.filename:
			filename = secure_filename(bg_file.filename)
			ext = os.path.splitext(filename)[1].lower()
			if ext not in ALLOWED_IMAGE_EXTS:
				flash('Background must be an image (png, jpg, jpeg, gif, webp).', 'error')
				return redirect(url_for('admin.system_customization'))

			safe_name = f"campus_{campus.id}_bg_{int(time.time())}{ext}"
			full_path = os.path.join(branding_dir, safe_name)
			bg_file.save(full_path)
			rel_path = os.path.join('uploads', 'branding', safe_name).replace('\\', '/')
			campus.campus_landing_bg_path = rel_path
		elif bg_url:
			campus.campus_landing_bg_path = bg_url

		db.session.commit()

		# If campus name changed, create notifications for all super_super_admins and broadcast
		if old_name_snapshot and campus.name and old_name_snapshot != campus.name:
			# Find super_super_admin users to notify
			super_supers = User.query.filter_by(role='super_super_admin', is_active=True).all()
			from datetime import datetime
			payload = {
				'campus_id': campus.id,
				'old_name': old_name_snapshot,
				'new_name': campus.name,
				'updated_by': {
					'id': current_user.id,
					'name': f"{current_user.first_name} {current_user.last_name}"
				},
				'timestamp': datetime.utcnow().isoformat()
			}
			for admin in super_supers:
				Notification.create_campus_update_notification(
					user_id=admin.id,
					campus=campus,
					old_name=old_name_snapshot,
					new_name=campus.name,
					updated_by_user=current_user
				)
			db.session.commit()
			# Broadcast to connected super admins via Socket.IO
			try:
				broadcast_campus_name_update(payload)
			except Exception:
				pass
		flash('Campus details and customization updated successfully.', 'success')
	except Exception as e:
		db.session.rollback()
		flash(f'Error updating customization: {str(e)}', 'error')

	return redirect(url_for('admin.system_customization'))
