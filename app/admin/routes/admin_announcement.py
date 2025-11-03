from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import db
from flask_wtf.csrf import CSRFProtect
from app.models import Announcement, Office, AuditLog, User, AnnouncementImage, Notification, OfficeAdmin
from datetime import datetime, timedelta
from sqlalchemy import desc
from app.admin import admin_bp
import os
from werkzeug.utils import secure_filename
from uuid import uuid4
try:
    from app.websockets.campus_admin import push_campus_admin_announcement
    from app.websockets.student import (
        push_student_announcement_public,
        push_student_announcement_to_office,
    )
    from app.websockets.office import (
        push_office_notification_to_office,
        push_office_notification_broadcast,
    )
except Exception:
    push_campus_admin_announcement = None
    push_student_announcement_public = None
    push_student_announcement_to_office = None
    push_office_notification_to_office = None
    push_office_notification_broadcast = None


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(image_file):
    """Save image file and return the path"""
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        # Create unique filename to prevent overwriting
        unique_filename = f"{uuid4().hex}_{filename}"
        # Ensure directory exists (absolute path under Flask static folder)
        static_root = getattr(current_app, 'static_folder', None) or os.path.join(os.getcwd(), 'static')
        upload_folder = os.path.join(static_root, 'uploads', 'announcements')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(upload_folder, unique_filename)
        image_file.save(file_path)
        
        # Return the relative path for database storage
        relative_path = os.path.join('uploads', 'announcements', unique_filename)
        return relative_path.replace(os.sep, '/')
    return None


@admin_bp.route('/admin_announcement', methods=['GET'])
@login_required
def announcement():
    """Show the announcement management page"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = request.args.get('office_id', type=int)
    visibility = request.args.get('visibility')
    date_range = request.args.get('date_range')
    page = request.args.get('page', 1, type=int)
    per_page = 10 
    
    query = Announcement.query

    if office_id:
        query = query.filter(Announcement.target_office_id == office_id)
    
    if visibility == 'public':
        query = query.filter(Announcement.is_public == True)
    elif visibility == 'office':
        query = query.filter(Announcement.is_public == False)
    
    if date_range:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        if date_range == 'today':
            query = query.filter(Announcement.created_at >= today)
        elif date_range == 'week':
            start_of_week = today - timedelta(days=today.weekday())
            query = query.filter(Announcement.created_at >= start_of_week)
        elif date_range == 'month':
            start_of_month = today.replace(day=1)
            query = query.filter(Announcement.created_at >= start_of_month)

    if current_user.role == 'office_admin':
        query = query.filter((Announcement.target_office_id == current_user.office_admin.office_id) | 
                             (Announcement.is_public == True))
    
    query = query.order_by(desc(Announcement.created_at))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    announcements = pagination.items
    
    offices = Office.query.all()
    
    return render_template('admin/admin_announcement.html', 
                           announcements=announcements,
                           offices=offices,
                           pagination=pagination,
                           current_page=page,
                           total_pages=pagination.pages,
                           prev_page=pagination.prev_num,
                           next_page=pagination.next_num)


@admin_bp.route('/create_announcement', methods=['POST'])
@login_required
def create_announcement():
    """Create a new announcement with images"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        flash('You do not have permission to create announcements.', 'error')
        return redirect(url_for('admin.announcement'))
    
    try:
        title = request.form.get('title')
        content = request.form.get('content')
        visibility = request.form.get('visibility')
        
        if not title or not content or not visibility:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('admin.announcement'))
        
        new_announcement = Announcement(
            author_id=current_user.id,
            title=title,
            content=content,
            is_public=(visibility == 'public')
        )
        
        if visibility == 'office':
            target_office_id = request.form.get('target_office_id', type=int)
            if not target_office_id:
                flash('Please select a target office.', 'error')
                return redirect(url_for('admin.announcement'))
            
            if current_user.role == 'office_admin' and target_office_id != current_user.office_admin.office_id:
                flash('You can only create announcements for your own office.', 'error')
                return redirect(url_for('admin.announcement'))
                
            new_announcement.target_office_id = target_office_id
        
        db.session.add(new_announcement)
        db.session.flush()  # Flush to get the announcement ID for image association
        
        # Handle image uploads
        if 'images[]' in request.files:
            image_files = request.files.getlist('images[]')
            captions = request.form.getlist('captions[]')
            display_orders = request.form.getlist('display_orders[]')
            
            for i, image_file in enumerate(image_files):
                if image_file and image_file.filename:
                    image_path = save_image(image_file)
                    if image_path:
                        caption = captions[i] if i < len(captions) else ""
                        order = int(display_orders[i]) if i < len(display_orders) and display_orders[i] else 0
                        
                        image = AnnouncementImage(
                            announcement_id=new_announcement.id,
                            image_path=image_path,
                            caption=caption,
                            display_order=order
                        )
                        db.session.add(image)
        
        if current_user.role == 'super_admin':
            log = AuditLog.log_action(
                actor=current_user,
                action="Created Announcement",
                target_type="announcement",
                office=Office.query.get(new_announcement.target_office_id) if new_announcement.target_office_id else None,
                status="Created",
                is_success=True
            )
        
        db.session.commit()

        # After commit: create campus admin notifications & broadcast real-time
        try:
            # Also create Office Admin notifications so Office module has persisted items
            try:
                from app.utils.smart_notifications import SmartNotificationManager
                if new_announcement.is_public:
                    # Notify all office admins except the author
                    office_admins = OfficeAdmin.query.filter(OfficeAdmin.user_id != current_user.id).all()
                    for oa in office_admins:
                        SmartNotificationManager.create_announcement_notification(new_announcement, oa.user_id)
                else:
                    # Target a specific office's admins
                    if new_announcement.target_office_id:
                        office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(
                            new_announcement.target_office_id,
                            exclude_user_id=current_user.id
                        )
                        for uid in office_admin_user_ids:
                            SmartNotificationManager.create_announcement_notification(new_announcement, uid)
            except Exception:
                db.session.rollback()

            # Determine campus context
            campus_id = None
            if new_announcement.target_office_id:
                office = Office.query.get(new_announcement.target_office_id)
                if office:
                    campus_id = office.campus_id
            if not campus_id and current_user.role == 'super_admin':
                campus_id = current_user.campus_id
            if not campus_id and current_user.role == 'office_admin':
                campus_id = current_user.office_admin.office.campus_id if current_user.office_admin else None

            if campus_id:
                # Collect campus admins except author
                campus_admins = User.query.filter_by(role='super_admin', campus_id=campus_id).all()
                payload = {
                    'title': new_announcement.title,
                    'content': (new_announcement.content[:140] + '...') if len(new_announcement.content) > 140 else new_announcement.content,
                    'announcement_id': new_announcement.id,
                    'author': current_user.get_full_name(),
                    'author_role': current_user.role,
                    'timestamp': new_announcement.created_at.isoformat(),
                    'is_public': new_announcement.is_public,
                    'target_office_id': new_announcement.target_office_id,
                    'campus_id': campus_id,
                    'author_id': current_user.id
                }
                # Create per-user Notification rows (type campus_announcement)
                created_any = False
                for admin_user in campus_admins:
                    if admin_user.id == current_user.id:
                        continue
                    notif = Notification(
                        user_id=admin_user.id,
                        title=f"New Announcement: {new_announcement.title[:60]}",
                        message=f"Posted by {payload['author']}",
                        notification_type='campus_announcement',
                        announcement_id=new_announcement.id,
                        is_read=False,
                        created_at=new_announcement.created_at,
                        link=f"/admin/admin_announcement#ann-{new_announcement.id}"
                    )
                    db.session.add(notif)
                    created_any = True
                if created_any:
                    db.session.commit()
                # Broadcast websocket event
                if push_campus_admin_announcement:
                    push_campus_admin_announcement(campus_id, payload)
                # Office module real-time notification for admins (per-user with notification_id)
                try:
                    from app.websockets.office import push_office_notification_to_user
                    from app.utils.smart_notifications import SmartNotificationManager
                    def emit_to_user(uid: int):
                        try:
                            notif = Notification.query.filter_by(user_id=uid, announcement_id=new_announcement.id, notification_type='announcement').order_by(Notification.created_at.desc()).first()
                            payload = {
                                'category': 'announcement',
                                'type': 'announcement',
                                'title': f"New Announcement: {new_announcement.title[:60]}",
                                'message': (new_announcement.content[:160] + '...') if len(new_announcement.content) > 160 else new_announcement.content,
                                'announcement_id': new_announcement.id,
                                'notification_id': getattr(notif, 'id', None),
                                'created_at': new_announcement.created_at.strftime('%b %d, %H:%M'),
                                'link': f"/admin/admin_announcement#ann-{new_announcement.id}"
                            }
                            if push_office_notification_to_user:
                                push_office_notification_to_user(uid, payload)
                        except Exception:
                            pass
                    if new_announcement.is_public:
                        admins = OfficeAdmin.query.filter(OfficeAdmin.user_id != current_user.id).all()
                        for oa in admins:
                            emit_to_user(oa.user_id)
                    else:
                        if new_announcement.target_office_id:
                            uids = SmartNotificationManager.get_office_admin_for_notification(new_announcement.target_office_id, exclude_user_id=current_user.id)
                            for uid in uids:
                                emit_to_user(uid)
                except Exception:
                    pass
                # Broadcast to students (public or office-targeted)
                student_payload = {
                    'notification_type': 'announcement',
                    'title': new_announcement.title,
                    'message': (new_announcement.content[:140] + '...') if len(new_announcement.content) > 140 else new_announcement.content,
                    'announcement_id': new_announcement.id,
                    'timestamp': new_announcement.created_at.isoformat(),
                }
                if new_announcement.is_public:
                    if push_student_announcement_public:
                        push_student_announcement_public(dict(student_payload))
                else:
                    if new_announcement.target_office_id and push_student_announcement_to_office:
                        push_student_announcement_to_office(new_announcement.target_office_id, dict(student_payload))
        except Exception as _e:
            db.session.rollback()
            # Swallow errors to not break UX; could log

        flash('Announcement created successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating announcement: {str(e)}', 'error')
    
    return redirect(url_for('admin.announcement'))


@admin_bp.route('/get_announcement/<int:announcement_id>', methods=['GET'])
@login_required
def get_announcement(announcement_id):
    """Get announcement data for editing"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    announcement = Announcement.query.get_or_404(announcement_id)

    if current_user.role == 'office_admin':
        if not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Get images associated with this announcement
    images = AnnouncementImage.query.filter_by(announcement_id=announcement_id).all()
    images_data = [{
        'id': image.id,
        'image_path': url_for('static', filename=image.image_path),
        'caption': image.caption,
        'display_order': image.display_order
    } for image in images]
    
    return jsonify({
        'id': announcement.id,
        'title': announcement.title,
        'content': announcement.content,
        'is_public': announcement.is_public,
        'target_office_id': announcement.target_office_id,
        'images': images_data
    })


@admin_bp.route('/update_announcement', methods=['POST'])
@login_required
def update_announcement():
    """Update an existing announcement with images"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        flash('You do not have permission to update announcements.', 'error')
        return redirect(url_for('admin.announcement'))
    
    try:
        announcement_id = request.form.get('announcement_id', type=int)
        announcement = Announcement.query.get_or_404(announcement_id)

        if current_user.role == 'office_admin' and not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            flash('You do not have permission to update this announcement.', 'error')
            return redirect(url_for('admin.announcement'))
        
        title = request.form.get('title')
        content = request.form.get('content')
        visibility = request.form.get('visibility')
        
        if not title or not content or not visibility:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('admin.announcement'))
        
        announcement.title = title
        announcement.content = content
        announcement.is_public = (visibility == 'public')

        if visibility == 'office':
            target_office_id = request.form.get('target_office_id', type=int)
            if not target_office_id:
                flash('Please select a target office.', 'error')
                return redirect(url_for('admin.announcement'))
            
            if current_user.role == 'office_admin' and target_office_id != current_user.office_admin.office_id:
                flash('You can only create announcements for your own office.', 'error')
                return redirect(url_for('admin.announcement'))
                
            announcement.target_office_id = target_office_id
        else:
            announcement.target_office_id = None
        
        # Handle new image uploads
        if 'new_images[]' in request.files:
            image_files = request.files.getlist('new_images[]')
            captions = request.form.getlist('new_captions[]')
            display_orders = request.form.getlist('new_display_orders[]')
            
            for i, image_file in enumerate(image_files):
                if image_file and image_file.filename:
                    image_path = save_image(image_file)
                    if image_path:
                        caption = captions[i] if i < len(captions) else ""
                        order = int(display_orders[i]) if i < len(display_orders) and display_orders[i] else 0
                        
                        image = AnnouncementImage(
                            announcement_id=announcement.id,
                            image_path=image_path,
                            caption=caption,
                            display_order=order
                        )
                        db.session.add(image)
        
        # Handle updates to existing images (captions and display orders)
        existing_image_ids = request.form.getlist('existing_image_ids[]')
        existing_captions = request.form.getlist('existing_captions[]')
        existing_display_orders = request.form.getlist('existing_display_orders[]')
        
        for i, image_id in enumerate(existing_image_ids):
            if image_id:
                image = AnnouncementImage.query.get(int(image_id))
                if image and image.announcement_id == announcement.id:
                    if i < len(existing_captions):
                        image.caption = existing_captions[i]
                    if i < len(existing_display_orders) and existing_display_orders[i]:
                        image.display_order = int(existing_display_orders[i])
        
        if current_user.role == 'super_admin':
            log = AuditLog.log_action(
                actor=current_user,
                action="Updated Announcement",
                target_type="announcement",
                office=Office.query.get(announcement.target_office_id) if announcement.target_office_id else None,
                status="Updated",
                is_success=True
            )
        
        db.session.commit()

        # Broadcast update (optional) – treat as new for campus admins
        try:
            campus_id = None
            if announcement.target_office_id:
                office = Office.query.get(announcement.target_office_id)
                if office:
                    campus_id = office.campus_id
            if not campus_id and current_user.role == 'super_admin':
                campus_id = current_user.campus_id
            if not campus_id and current_user.role == 'office_admin':
                campus_id = current_user.office_admin.office.campus_id if current_user.office_admin else None
            if campus_id and push_campus_admin_announcement:
                push_campus_admin_announcement(campus_id, {
                    'title': announcement.title + ' (Updated)',
                    'content': (announcement.content[:140] + '...') if len(announcement.content) > 140 else announcement.content,
                    'announcement_id': announcement.id,
                    'author': current_user.get_full_name(),
                    'author_role': current_user.role,
                    'timestamp': datetime.utcnow().isoformat(),
                    'is_public': announcement.is_public,
                    'target_office_id': announcement.target_office_id,
                    'campus_id': campus_id,
                    'author_id': current_user.id,
                    'updated': True
                })
        except Exception:
            pass

        flash('Announcement updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating announcement: {str(e)}', 'error')
    
    return redirect(url_for('admin.announcement'))


@admin_bp.route('/delete_announcement', methods=['POST'])
@login_required
def delete_announcement():
    """Delete an announcement and its images"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        flash('You do not have permission to delete announcements.', 'error')
        return redirect(url_for('admin.announcement'))
    
    try:
        announcement_id = request.form.get('announcement_id', type=int)
        announcement = Announcement.query.get_or_404(announcement_id)
        
        if current_user.role == 'office_admin' and not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            flash('You do not have permission to delete this announcement.', 'error')
            return redirect(url_for('admin.announcement'))
        
        # Delete associated images first
        images = AnnouncementImage.query.filter_by(announcement_id=announcement_id).all()
        for image in images:
            # Optionally delete the physical file
            try:
                static_root = getattr(current_app, 'static_folder', None) or os.path.join(os.getcwd(), 'static')
                file_path = os.path.join(static_root, image.image_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                # Log error but continue with database deletion
                print(f"Error removing image file: {str(e)}")
            
            db.session.delete(image)
        
        if current_user.role == 'super_admin':
            log = AuditLog.log_action(
                actor=current_user,
                action="Deleted Announcement",
                target_type="announcement",
                office=Office.query.get(announcement.target_office_id) if announcement.target_office_id else None,
                status="Deleted",
                is_success=True
            )
        
        db.session.delete(announcement)
        db.session.commit()
        flash('Announcement deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting announcement: {str(e)}', 'error')
    
    return redirect(url_for('admin.announcement'))


@admin_bp.route('/delete_announcement_image', methods=['POST'])
@login_required
def delete_announcement_image():
    """Delete an announcement image"""
    if current_user.role != 'super_admin' and current_user.role != 'office_admin':
        flash('You do not have permission to delete announcement images.', 'error')
        return redirect(url_for('admin.announcement'))
    
    try:
        image_id = request.form.get('image_id', type=int)
        announcement_id = request.form.get('announcement_id', type=int)
        
        image = AnnouncementImage.query.get_or_404(image_id)
        
        # Verify the image belongs to the specified announcement
        if image.announcement_id != announcement_id:
            flash('Invalid request.', 'error')
            return redirect(url_for('admin.announcement'))
        
        announcement = Announcement.query.get_or_404(announcement_id)
        
        # Check permission
        if current_user.role == 'office_admin' and not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            flash('You do not have permission to delete this image.', 'error')
            return redirect(url_for('admin.announcement'))
        
        # Delete the physical file
        try:
            static_root = getattr(current_app, 'static_folder', None) or os.path.join(os.getcwd(), 'static')
            file_path = os.path.join(static_root, image.image_path)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            # Log error but continue with database deletion
            print(f"Error removing image file: {str(e)}")
        
        db.session.delete(image)
        db.session.commit()
        
        flash('Image deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting image: {str(e)}', 'error')
    
    # Return to the edit announcement page
    return redirect(url_for('admin.announcement'))


@admin_bp.route('/api/notifications/mark-all-campus-announcements-read', methods=['POST'])
@login_required
def mark_all_campus_announcements_read():
    """Mark all campus announcement notifications as read for the current campus admin."""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        updated = Notification.query.filter_by(
            user_id=current_user.id,
            notification_type='campus_announcement',
            is_read=False
        ).update({ 'is_read': True })
        db.session.commit()
        # Count remaining unread after update (should be zero, but recompute for safety)
        unread_remaining = Notification.query.filter_by(
            user_id=current_user.id,
            notification_type='campus_announcement',
            is_read=False
        ).count()
        return jsonify({'status': 'ok', 'updated': updated, 'unread_remaining': unread_remaining})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/notifications/campus-announcements', methods=['GET'])
@login_required
def get_campus_announcement_notifications():
    """Return recent campus announcement notifications for the campus admin dropdown refresh.

    Query Params:
        limit (int, optional): Max number of notifications to return (default 8, max 25)
    Response: JSON list of notification objects with fields consumed by adminbase.js refresh logic.
    """
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        limit = request.args.get('limit', 8, type=int)
        if limit > 25:
            limit = 25
        notifications = (Notification.query
                          .filter_by(user_id=current_user.id, notification_type='campus_announcement')
                          .order_by(Notification.created_at.desc())
                          .limit(limit)
                          .all())
        payload = [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%b %d, %H:%M'),
                'link': n.link
            } for n in notifications
        ]
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/announcements', methods=['GET'])
@login_required
def get_announcements_api():
    """API endpoint to get announcements for a specific office or public announcements"""
    try:
        office_id = request.args.get('office_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        
        query = Announcement.query.filter(Announcement.is_public == True)
        
        if office_id:
            query = query.union(
                Announcement.query.filter(
                    Announcement.is_public == False,
                    Announcement.target_office_id == office_id
                )
            )
        
        query = query.order_by(desc(Announcement.created_at))
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        announcements = pagination.items
        
        result = {
            'announcements': [
                {
                    'id': a.id,
                    'title': a.title,
                    'content': a.content,
                    'is_public': a.is_public,
                    'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'author': User.query.get(a.author_id).get_full_name() if a.author_id else 'System',
                    'target_office': Office.query.get(a.target_office_id).name if a.target_office_id else None,
                    'images': [
                        {
                            'id': img.id,
                            'image_path': url_for('static', filename=img.image_path),
                            'caption': img.caption,
                            'display_order': img.display_order
                        } for img in AnnouncementImage.query.filter_by(announcement_id=a.id).order_by(AnnouncementImage.display_order).all()
                    ]
                }
                for a in announcements
            ],
            'pagination': {
                'current_page': page,
                'total_pages': pagination.pages,
                'total_items': pagination.total,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500