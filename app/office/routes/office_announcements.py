from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, AnnouncementImage, Notification
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
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
        # Ensure directory exists
        upload_folder = os.path.join('static', 'uploads', 'announcements')
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
        
        # Log the action
        log = AuditLog.log_action(
            actor=current_user,
            action="Created Announcement",
            target_type="announcement",
            office=Office.query.get(new_announcement.target_office_id) if new_announcement.target_office_id else None,
            status="Created",
            is_success=True
        )
        
        db.session.commit()
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
                file_path = os.path.join('app', 'static', image.image_path)
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
            file_path = os.path.join('app', 'static', image.image_path)
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
                    'author_name': Office.query.get(a.target_office_id).name if a.target_office_id else 'University Admin',
                    'office_name': Office.query.get(a.target_office_id).name if a.target_office_id else current_user.office_admin.office.name,
                    'target_office': Office.query.get(a.target_office_id).name if a.target_office_id else None,
                    'can_edit': a.author_id == current_user.id,
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