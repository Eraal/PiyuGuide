from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, AnnouncementImage, Notification
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import time  
from sqlalchemy import func, case, desc, or_ 
from app.office import office_bp
from app.utils import role_required
from app.office.routes.office_dashboard import get_office_context
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
        push_office_notification_to_user,
    )
except Exception:
    push_campus_admin_announcement = None
    push_student_announcement_public = None
    push_student_announcement_to_office = None
    push_office_notification_to_office = None
    push_office_notification_broadcast = None
    push_office_notification_to_user = None


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


@office_bp.route('/office-announcement')
@login_required
@role_required(['office_admin'])
def office_announcements():
    """Show the office announcement management page"""
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

    # Office admin can see public announcements and those specific to their office
    query = query.filter((Announcement.target_office_id == current_user.office_admin.office_id) | 
                         (Announcement.is_public == True))
    
    query = query.order_by(desc(Announcement.created_at))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    announcements = pagination.items
    
    offices = Office.query.all()
    
    # Get common context data
    context = get_office_context()
    
    return render_template('office/office_announcement.html', 
                           announcements=announcements,
                           offices=offices,
                           pagination=pagination,
                           current_page=page,
                           total_pages=pagination.pages,
                           prev_page=pagination.prev_num,
                           next_page=pagination.next_num,
                           **context)


@office_bp.route('/create-announcement', methods=['POST'])
@login_required
@role_required(['office_admin'])
def create_announcement():
    """Create a new announcement with images"""
    try:
        title = request.form.get('title')
        content = request.form.get('content')
        visibility = request.form.get('visibility')

        if not title or not content or not visibility:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('office.office_announcements'))

        new_announcement = Announcement(
            author_id=current_user.id,
            title=title,
            content=content,
            is_public=(visibility == 'public')
        )

        if visibility == 'office':
            # Force the target office to be the admin's own office
            new_announcement.target_office_id = current_user.office_admin.office_id

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

        # Create notifications for office admins using smart notification system
        from app.utils.smart_notifications import SmartNotificationManager

        if visibility == 'office' and new_announcement.target_office_id:
            # Notify all office admins in the target office (excluding the author)
            office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(
                new_announcement.target_office_id, exclude_user_id=current_user.id
            )

            for admin_user_id in office_admin_user_ids:
                SmartNotificationManager.create_announcement_notification(
                    new_announcement, admin_user_id
                )
        elif visibility == 'public':
            # For public announcements, notify all office admins in the system
            all_office_admins = OfficeAdmin.query.filter(
                OfficeAdmin.user_id != current_user.id
            ).all()

            for office_admin in all_office_admins:
                SmartNotificationManager.create_announcement_notification(
                    new_announcement, office_admin.user_id
                )

        # Log the action
        AuditLog.log_action(
            actor=current_user,
            action="Created Announcement",
            target_type="announcement",
            office=Office.query.get(new_announcement.target_office_id) if new_announcement.target_office_id else None,
            status="Created",
            is_success=True
        )

        db.session.commit()

        # Office module: real-time toast for office admins (per-user with notification_id)
        try:
            ann_link = f"/office/office-announcement#ann-{new_announcement.id}"
            def emit_to_user(uid: int):
                try:
                    notif = Notification.query.filter_by(user_id=uid, announcement_id=new_announcement.id, notification_type='announcement').order_by(Notification.created_at.desc()).first()
                    payload = {
                        'category': 'announcement',
                        'type': 'announcement',
                        'title': f"New Announcement: {title[:60]}",
                        'message': (content[:160] + '...') if len(content) > 160 else content,
                        'announcement_id': new_announcement.id,
                        'notification_id': getattr(notif, 'id', None),
                        'created_at': new_announcement.created_at.strftime('%b %d, %H:%M'),
                        'link': ann_link,
                    }
                    if push_office_notification_to_user:
                        push_office_notification_to_user(uid, payload)
                except Exception:
                    pass

            if visibility == 'office' and new_announcement.target_office_id:
                # Notify admins of the office (excluding author) – IDs already computed earlier
                try:
                    from app.utils.smart_notifications import SmartNotificationManager
                    office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(
                        new_announcement.target_office_id, exclude_user_id=current_user.id
                    )
                except Exception:
                    office_admin_user_ids = []
                for uid in office_admin_user_ids:
                    emit_to_user(uid)
            else:
                # Public: notify all office admins (excluding author)
                admins = OfficeAdmin.query.filter(OfficeAdmin.user_id != current_user.id).all()
                for oa in admins:
                    emit_to_user(oa.user_id)
        except Exception:
            pass

        # Real-time campus admin notifications (for campus admins of same campus)
        try:
            campus_id = current_user.office_admin.office.campus_id if current_user.office_admin else None
            if campus_id:
                campus_admins = User.query.filter_by(role='super_admin', campus_id=campus_id).all()
                payload = {
                    'kind': 'announcement',
                    'title': title,
                    'content': (content[:140] + '...') if len(content) > 140 else content,
                    'announcement_id': new_announcement.id,
                    'author': current_user.get_full_name(),
                    'author_role': current_user.role,
                    'timestamp': new_announcement.created_at.isoformat(),
                    'is_public': new_announcement.is_public,
                    'target_office_id': new_announcement.target_office_id,
                    'campus_id': campus_id,
                    'author_id': current_user.id
                }
                created_any = False
                for admin_user in campus_admins:
                    if admin_user.id == current_user.id:
                        continue
                    notif = Notification(
                        user_id=admin_user.id,
                        title=f"New Office Announcement: {title[:60]}",
                        message=f"{current_user.get_full_name()} posted an announcement",
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
                if push_campus_admin_announcement:
                    push_campus_admin_announcement(campus_id, payload)
        except Exception:
            db.session.rollback()

        # Broadcast to students in real-time and create light-weight per-student Notification rows
        try:
            # Compose rich payload with source office/author context
            try:
                author_name = current_user.get_full_name()
                author_role = current_user.role
                target_office_name = None
                campus_name = None
                if not new_announcement.is_public and new_announcement.target_office_id:
                    office_obj = Office.query.get(new_announcement.target_office_id)
                    if office_obj:
                        target_office_name = office_obj.name
                        campus_name = office_obj.campus.name if office_obj.campus else None
                posted_by_office_name = None
                if author_role == 'office_admin' and getattr(current_user, 'office_admin', None):
                    posted_by_office_name = getattr(current_user.office_admin.office, 'name', None)
                img_count = AnnouncementImage.query.filter_by(announcement_id=new_announcement.id).count()
            except Exception:
                author_name = getattr(current_user, 'first_name', 'User')
                author_role = getattr(current_user, 'role', 'user')
                target_office_name = None
                posted_by_office_name = None
                campus_name = None
                img_count = 0

            payload_common = {
                'kind': 'announcement',
                'notification_type': 'announcement',
                'title': title,
                'message': (content[:140] + '...') if len(content) > 140 else content,
                'announcement_id': new_announcement.id,
                'timestamp': new_announcement.created_at.isoformat(),
                'is_public': bool(new_announcement.is_public),
                'target_office_id': new_announcement.target_office_id,
                'target_office_name': target_office_name,
                'posted_by_office_name': posted_by_office_name,
                'campus_name': campus_name,
                'author_name': author_name,
                'author_role': author_role,
                'image_count': img_count,
                'link': f"/student/announcement/{new_announcement.id}",
                'api_link': f"/student/api/announcement/{new_announcement.id}",
            }
            if new_announcement.is_public:
                if push_student_announcement_public:
                    push_student_announcement_public(dict(payload_common))
            else:
                office_id = new_announcement.target_office_id
                if office_id and push_student_announcement_to_office:
                    push_student_announcement_to_office(office_id, dict(payload_common))

            # Persist Notifications for recently active students
            try:
                from datetime import timedelta
                from app.models import Student, Inquiry, Notification, Office as _Office
                recent_cutoff = datetime.utcnow() - timedelta(days=30)
                q = db.session.query(Student.user_id).distinct()
                if new_announcement.is_public:
                    q = (q.join(Inquiry, Inquiry.student_id == Student.id)
                         .filter(Inquiry.created_at >= recent_cutoff))
                else:
                    q = (q.join(Inquiry, Inquiry.student_id == Student.id)
                         .filter(Inquiry.office_id == new_announcement.target_office_id,
                                 Inquiry.created_at >= recent_cutoff))
                user_ids = [uid for (uid,) in q.limit(500).all()]
                office_name = None
                if not new_announcement.is_public and new_announcement.target_office_id:
                    try:
                        office_name = _Office.query.get(new_announcement.target_office_id).name
                    except Exception:
                        office_name = None
                notif_title = f"New Announcement{f' from {office_name}' if office_name else ''}"
                for uid in user_ids:
                    db.session.add(Notification(
                        user_id=uid,
                        title=notif_title,
                        message=(f"{author_name} • {title}")[:200],
                        notification_type='announcement',
                        source_office_id=new_announcement.target_office_id,
                        announcement_id=new_announcement.id,
                        is_read=False,
                        created_at=new_announcement.created_at,
                        link=f"/student/announcement/{new_announcement.id}"
                    ))
                if user_ids:
                    db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception:
            pass

        flash('Announcement created successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating announcement: {str(e)}', 'error')

    return redirect(url_for('office.office_announcements'))


@office_bp.route('/get-announcement/<int:announcement_id>', methods=['GET'])
@login_required
@role_required(['office_admin'])
def get_announcement(announcement_id):
    """Get announcement data for editing"""
    announcement = Announcement.query.get_or_404(announcement_id)

    # Check if the office admin has permission to edit this announcement
    if not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
        return jsonify({'error': 'You do not have permission to edit this announcement'}), 403
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
        'office_name': Office.query.get(announcement.target_office_id).name if announcement.target_office_id else current_user.office_admin.office.name,
        'images': images_data
    })


@office_bp.route('/update-announcement', methods=['POST'])
@login_required
@role_required(['office_admin'])
def update_announcement():
    """Update an existing announcement with images"""
    try:
        announcement_id = request.form.get('announcement_id', type=int)
        announcement = Announcement.query.get_or_404(announcement_id)

        # Check if the office admin has permission to update this announcement
        if not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            flash('You do not have permission to update this announcement.', 'error')
            return redirect(url_for('office.office_announcements'))
        
        # Check if this is their own announcement (only allow editing own announcements)
        if announcement.author_id != current_user.id:
            flash('You can only edit announcements that you created.', 'error')
            return redirect(url_for('office.office_announcements'))
        
        title = request.form.get('title')
        content = request.form.get('content')
        visibility = request.form.get('visibility')
        
        if not title or not content or not visibility:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('office.office_announcements'))
        
        announcement.title = title
        announcement.content = content
        announcement.is_public = (visibility == 'public')

        if visibility == 'office':
            # Force the target office to be the admin's own office
            announcement.target_office_id = current_user.office_admin.office_id
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
        
        # Log the action
        log = AuditLog.log_action(
            actor=current_user,
            action="Updated Announcement",
            target_type="announcement",
            office=Office.query.get(announcement.target_office_id) if announcement.target_office_id else None,
            status="Updated",
            is_success=True
        )
        
        db.session.commit()
        flash('Announcement updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating announcement: {str(e)}', 'error')
    
    return redirect(url_for('office.office_announcements'))


@office_bp.route('/delete-announcement', methods=['POST'])
@login_required
@role_required(['office_admin'])
def delete_announcement():
    """Delete an announcement and its images"""
    try:
        announcement_id = request.form.get('announcement_id', type=int)
        announcement = Announcement.query.get_or_404(announcement_id)
        
        # Check if the office admin has permission to delete this announcement
        if not announcement.is_public and announcement.target_office_id != current_user.office_admin.office_id:
            flash('You do not have permission to delete this announcement.', 'error')
            return redirect(url_for('office.office_announcements'))
        
        # Ensure they can only delete their own announcements
        if announcement.author_id != current_user.id:
            flash('You can only delete announcements that you created.', 'error')
            return redirect(url_for('office.office_announcements'))
        
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
        
        # Log the action
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
    
    return redirect(url_for('office.office_announcements'))


@office_bp.route('/delete-announcement-image', methods=['POST'])
@login_required
@role_required(['office_admin'])
def delete_announcement_image():
    """Delete an announcement image"""
    try:
        image_id = request.form.get('image_id', type=int)
        announcement_id = request.form.get('announcement_id', type=int)
        
        image = AnnouncementImage.query.get_or_404(image_id)
        
        # Verify the image belongs to the specified announcement
        if image.announcement_id != announcement_id:
            flash('Invalid request.', 'error')
            return redirect(url_for('office.office_announcements'))
        
        announcement = Announcement.query.get_or_404(announcement_id)
        
        # Check permission - must be their own announcement
        if announcement.author_id != current_user.id:
            flash('You can only modify announcements that you created.', 'error')
            return redirect(url_for('office.office_announcements'))
        
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
    return redirect(url_for('office.office_announcements'))


@office_bp.route('/api/office-announcements', methods=['GET'])
@login_required
@role_required(['office_admin'])
def get_office_announcements_api():
    """API endpoint to get announcements for the office"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)

        # Get public announcements and announcements for this office
        query = Announcement.query.filter(
            (Announcement.is_public == True) |
            (Announcement.target_office_id == current_user.office_admin.office_id)
        ).order_by(desc(Announcement.created_at))

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        announcements = pagination.items

        def resolve_avatar(author):
            try:
                if not author:
                    return url_for('static', filename='images/default.jpg')
                raw = getattr(author, 'profile_pic', None)
                if raw and str(raw).strip().lower().startswith(('http://', 'https://')):
                    return raw
                path = getattr(author, 'profile_pic_path', None)
                if path:
                    return url_for('static', filename=path)
                return url_for('static', filename='images/default.jpg')
            except Exception:
                return url_for('static', filename='images/default.jpg')

        data = []
        for a in announcements:
            images = (
                AnnouncementImage.query
                .filter_by(announcement_id=a.id)
                .order_by(AnnouncementImage.display_order, AnnouncementImage.id)
                .all()
            )
            data.append({
                'id': a.id,
                'title': a.title,
                'content': a.content,
                'is_public': a.is_public,
                'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'author_id': a.author_id,
                'author_name': (a.author.get_full_name() if a.author else 'System'),
                'author_role': (a.author.role if a.author else 'system'),
                'author_avatar': resolve_avatar(a.author),
                'office_name': (Office.query.get(a.target_office_id).name if a.target_office_id else None),
                'target_office': (Office.query.get(a.target_office_id).name if a.target_office_id else None),
                'can_edit': a.author_id == current_user.id,
                'images': [
                    {
                        'id': img.id,
                        'image_path': url_for('static', filename=img.image_path),
                        'caption': img.caption,
                        'display_order': img.display_order
                    }
                    for img in images
                ]
            })

        result = {
            'announcements': data,
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


    @office_bp.route('/announcement/<int:announcement_id>', methods=['GET'])
    @login_required
    @role_required(['office_admin'])
    def view_announcement(announcement_id: int):
        """Render a dedicated page showing a single announcement in full.

        Visibility rules:
        - Public announcements are visible to all office admins.
        - Private (office-targeted) announcements are only visible to admins
          of the target office.
        """
        # Fetch announcement or 404
        announcement = Announcement.query.get_or_404(announcement_id)

        # Enforce visibility for office admins
        if not announcement.is_public:
            current_office_id = getattr(getattr(current_user, 'office_admin', None), 'office_id', None)
            if not current_office_id or announcement.target_office_id != current_office_id:
                flash('You do not have permission to view this announcement.', 'error')
                return redirect(url_for('office.office_announcements'))

        # Prepare template context (notifications, counts, etc.)
        context = get_office_context()

        # Audit trail (best-effort; ignore failures)
        try:
            AuditLog.log_action(
                actor=current_user,
                action='Viewed Announcement',
                target_type='announcement',
                target_id=announcement.id,
                office=announcement.target_office or getattr(getattr(current_user, 'office_admin', None), 'office', None),
                status='viewed',
                is_success=True,
                ip_address=getattr(request, 'remote_addr', None),
                user_agent=getattr(getattr(request, 'user_agent', None), 'string', None)
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

        return render_template('office/view_announcement.html', announcement=announcement, **context)