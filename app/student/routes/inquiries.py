from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc, or_
from app.student import student_bp
from app.models import (
    Inquiry, InquiryMessage, Student, User, Office, 
    ConcernType, OfficeConcernType, InquiryConcern, 
    InquiryAttachment, StudentActivityLog, Notification, OfficeAdmin
)
from app.extensions import db
from app.utils import role_required
import os
from werkzeug.utils import secure_filename

# Import dashboard broadcasting function
try:
    from app.websockets.dashboard import broadcast_new_inquiry
except ImportError:
    broadcast_new_inquiry = None

def save_attachment(file, folder_name):
    """Save an uploaded file to the specified folder and return the file path."""
    upload_folder = os.path.join('static', 'uploads', folder_name)
    os.makedirs(upload_folder, exist_ok=True)
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(upload_folder, unique_filename)
    # Fix invalid escape sequence by using raw string or double backslashes
    file.save(os.path.join(r'd:\SystemProject\KapiyuGuide_System', file_path))
    return file_path

# Inquiry list view
@student_bp.route('/inquiries')
@login_required
@role_required(['student'])
def inquiries():
    """View all inquiries submitted by the student"""    # Get query parameters for filtering
    status = request.args.get('status', 'all')
    office_id = request.args.get('office_id', 'all')
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Base query
    query = Inquiry.query.filter_by(student_id=student.id)
    
    # Apply status filter if provided
    if status != 'all':
        query = query.filter(Inquiry.status == status)
    
    # Apply office filter if provided
    if office_id != 'all':
        query = query.filter(Inquiry.office_id == office_id)    # Apply search filter if provided
    if search:
        # Search in both subject and first message content
        query = query.join(InquiryMessage, Inquiry.id == InquiryMessage.inquiry_id, isouter=True).filter(
            or_(
                Inquiry.subject.ilike(f'%{search}%'),
                InquiryMessage.content.ilike(f'%{search}%')
            )
        ).distinct()
    
    # Order by most recent first
    query = query.order_by(desc(Inquiry.created_at))
    
    # Paginate results
    inquiries_paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get all offices for filter dropdown
    offices = Office.query.all()
    
    # Calculate statistics for sidebar
    stats = {
        'total': Inquiry.query.filter_by(student_id=student.id).count(),
        'pending': Inquiry.query.filter_by(student_id=student.id, status='pending').count(),
        'in_progress': Inquiry.query.filter_by(student_id=student.id, status='in_progress').count(),
        'resolved': Inquiry.query.filter_by(student_id=student.id, status='resolved').count()
    }
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed inquiries list",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/inquiries.html',
        inquiries=inquiries_paginated.items,
        pagination=inquiries_paginated,
        offices=offices,
        stats=stats,
        current_status=status,
        current_office=office_id,
        current_search=search,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

# View a single inquiry with messages
@student_bp.route('/inquiry/<int:inquiry_id>')
@login_required
@role_required(['student'])
def view_inquiry(inquiry_id):
    """View a specific inquiry with its conversation history"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the inquiry and verify ownership
    inquiry = Inquiry.query.filter_by(
        id=inquiry_id,
        student_id=student.id
    ).first_or_404()
    
    # Get latest 6 messages for this inquiry for initial load
    messages = InquiryMessage.query.filter_by(
        inquiry_id=inquiry.id
    ).order_by(desc(InquiryMessage.created_at)).limit(6).all()
    
    # Reverse the messages to display in chronological order
    messages = messages[::-1]
    
    # Get total message count for pagination
    total_messages = InquiryMessage.query.filter_by(inquiry_id=inquiry.id).count()
    
    # Get related inquiries (same office)
    related_inquiries = Inquiry.query.filter(
        Inquiry.student_id == student.id,
        Inquiry.office_id == inquiry.office_id,
        Inquiry.id != inquiry.id
    ).order_by(desc(Inquiry.created_at)).limit(3).all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Viewed inquiry #{inquiry.id}",
        related_id=inquiry.id,
        related_type="inquiry",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/view_inquiry.html',
        inquiry=inquiry,
        messages=messages,
        total_messages=total_messages,
        related_inquiries=related_inquiries,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        has_more_messages=(total_messages > 6)
    )

# Submit inquiry to specific office
@student_bp.route('/office/<int:office_id>/submit-inquiry')
@login_required
@role_required(['student'])
def submit_inquiry(office_id):
    """Display a dedicated form for submitting an inquiry to a specific office"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the office
    office = Office.query.get_or_404(office_id)
    
    # Get concern types for this office
    concern_types = ConcernType.query.join(OfficeConcernType).filter(
        OfficeConcernType.office_id == office_id
    ).all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Viewed submission form for {office.name}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/submit_inquiry.html',
        office=office,
        concern_types=concern_types,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

# Create a new inquiry
@student_bp.route('/create-inquiry', methods=['POST'])
@login_required
@role_required(['student'])
def create_inquiry():
    """Submit a new inquiry to an office"""
    try:
        # Get form data
        office_id = request.form.get('office_id')
        subject = request.form.get('subject')
        message = request.form.get('message')
        concern_type_id = request.form.get('concern_type_id')
        other_concern = request.form.get('other_concern')

        # Validate required fields
        if not office_id or not subject or not message:
            flash('Please fill all required fields', 'error')
            return redirect(url_for('student.inquiries'))

        # Ensure office_id is valid
        office = Office.query.get(office_id)
        if not office:
            flash('Selected office does not exist.', 'error')
            return redirect(url_for('student.inquiries'))

        # Get the student record
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()

        # Create new inquiry
        new_inquiry = Inquiry(
            student_id=student.id,
            office_id=int(office_id),
            subject=subject,
            status='pending',
            created_at=datetime.utcnow()
        )
        db.session.add(new_inquiry)
        db.session.flush()  # Get the inquiry ID for attachments and concern types

        # Add first message
        initial_message = InquiryMessage(
            inquiry_id=new_inquiry.id,
            sender_id=current_user.id,
            content=message,
            created_at=datetime.utcnow()
        )
        db.session.add(initial_message)
        db.session.flush()  # Flush to get message ID

        # Add concern type if provided
        if concern_type_id:
            # Check if concern type allows "other" specification
            concern_type = ConcernType.query.get(concern_type_id)
            if concern_type:
                concern = InquiryConcern(
                    inquiry_id=new_inquiry.id,
                    concern_type_id=int(concern_type_id),
                    other_specification=other_concern if concern_type.allows_other and other_concern else None
                )
                db.session.add(concern)

        # Handle attachments if any
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename:
                    file_path = save_attachment(file, 'inquiries')
                    if file_path:
                        # Create file attachment with proper fields
                        attachment = InquiryAttachment(
                            filename=secure_filename(file.filename),
                            file_path=file_path,
                            file_size=len(file.read()),
                            file_type=file.content_type if hasattr(file, 'content_type') else None,
                            uploaded_by_id=current_user.id,  # Pass the user ID to uploaded_by_id
                            uploaded_at=datetime.utcnow(),
                            inquiry_id=new_inquiry.id
                        )
                        # Reset file pointer after reading size
                        file.seek(0)
                        db.session.add(attachment)        # Log this activity
        log_entry = StudentActivityLog.log_action(
            student=student,
            action="Created new inquiry",
            related_id=new_inquiry.id,
            related_type="inquiry",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )

        db.session.commit()

        # Broadcast new inquiry to dashboard for real-time updates
        if broadcast_new_inquiry:
            try:
                broadcast_new_inquiry(new_inquiry)
            except Exception as e:
                # Log error but don't fail the inquiry creation
                print(f"Failed to broadcast new inquiry: {e}")

        flash('Inquiry submitted successfully', 'success')
        return redirect(url_for('student.view_inquiry', inquiry_id=new_inquiry.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating inquiry: {str(e)}', 'error')
        return redirect(url_for('student.inquiries'))

# Add message to an existing inquiry
@student_bp.route('/inquiry/<int:inquiry_id>/reply', methods=['POST'])
@login_required
@role_required(['student'])
def reply_to_inquiry(inquiry_id):
    """Add a reply to an existing inquiry conversation"""
    try:
        # Get form data
        message = request.form.get('message')
        
        if not message:
            flash('Message cannot be empty', 'error')
            return redirect(url_for('student.view_inquiry', inquiry_id=inquiry_id))
        
        # Get the student record
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        
        # Get the inquiry and verify ownership
        inquiry = Inquiry.query.filter_by(
            id=inquiry_id,
            student_id=student.id
        ).first_or_404()
        
        # Add new message with status tracking
        new_message = InquiryMessage(
            inquiry_id=inquiry.id,
            sender_id=current_user.id,
            content=message,
            status='sent',  # Initial status is 'sent'
            created_at=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.flush()  # Get the message ID for attachments
        
        # Update inquiry status if it was resolved
        if inquiry.status == 'resolved':
            inquiry.status = 'reopened'
            
            # Update the last_activity timestamp for better tracking
            inquiry.last_activity = datetime.utcnow()
        
        # Handle attachments if any
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename:
                    file_path = save_attachment(file, 'inquiries')
                    if file_path:
                        # Create file attachment with proper fields
                        from app.models import MessageAttachment
                        attachment = MessageAttachment(
                            filename=secure_filename(file.filename),
                            file_path=file_path,
                            file_size=len(file.read()),
                            file_type=file.content_type if hasattr(file, 'content_type') else None,
                            uploaded_by_id=current_user.id,
                            uploaded_at=datetime.utcnow(),
                            message_id=new_message.id
                        )
                        # Reset file pointer after reading size
                        file.seek(0)
                        db.session.add(attachment)
        
        # Create notification for office admin
        # Find office admins for this inquiry's office
        office_admins = OfficeAdmin.query.filter_by(office_id=inquiry.office_id).all()
        for admin in office_admins:
            notification = Notification(
                user_id=admin.user_id,
                title="New Student Reply",
                message=f"Student {student.user.get_full_name()} replied to inquiry '{inquiry.subject}'",
                is_read=False
            )
            db.session.add(notification)
        
        # Log this activity using the log_action helper method
        log_entry = StudentActivityLog.log_action(
            student=student,
            action=f"Replied to inquiry",
            related_id=inquiry.id,
            related_type="inquiry",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )
        
        db.session.commit()
        
        # Emit WebSocket event for real-time updates if the websocket module is available
        # WebSocket functionality has been removed
        # Previously: emit_inquiry_reply(new_message)
        
        # Removed flash message that was causing popup notifications
        return redirect(url_for('student.view_inquiry', inquiry_id=inquiry_id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error sending reply: {str(e)}', 'error')
        return redirect(url_for('student.view_inquiry', inquiry_id=inquiry_id))

@student_bp.route('/api/inquiry/<int:inquiry_id>/messages', methods=['GET'])
@login_required
@role_required(['student'])
def get_older_messages(inquiry_id):
    """API to fetch older messages for infinite scrolling"""
    try:
        # Get the student record
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        
        # Get the inquiry and verify ownership
        inquiry = Inquiry.query.filter_by(
            id=inquiry_id,
            student_id=student.id
        ).first_or_404()
        
        # Get pagination parameters
        before_id = request.args.get('before_id', type=int)
        limit = request.args.get('limit', 6, type=int)
        
        # Query for older messages
        query = InquiryMessage.query.filter_by(
            inquiry_id=inquiry.id
        )
        
        # If we have a before_id, only get messages older than that
        if before_id:
            oldest_message = InquiryMessage.query.get(before_id)
            if oldest_message:
                query = query.filter(InquiryMessage.created_at < oldest_message.created_at)
        
        # Get messages in descending order and limit
        messages = query.order_by(desc(InquiryMessage.created_at)).limit(limit).all()
        
        # Reverse the messages to display in chronological order
        messages = messages[::-1]
        
        # Serialize messages data for JSON response
        messages_data = []
        for message in messages:
            sender = User.query.get(message.sender_id)
            is_student = sender.id == current_user.id
            
            messages_data.append({
                'id': message.id,
                'content': message.content,
                'timestamp': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender_name': sender.get_full_name() if sender else 'Unknown',
                'is_student': is_student,
                'status': message.status
            })
        
        return jsonify({
            'success': True,
            'messages': messages_data,
            'has_more': len(messages) >= limit
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching messages: {str(e)}'
        }), 500