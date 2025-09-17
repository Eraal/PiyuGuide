from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc, or_
from app.student import student_bp
from app.models import (
    Inquiry, InquiryMessage, Student, User, Office, 
    ConcernType, OfficeConcernType, InquiryConcern, 
    InquiryAttachment, StudentActivityLog, Notification, OfficeAdmin, MessageAttachment
)
from app.extensions import db
from app.utils import role_required
import os
from werkzeug.utils import secure_filename
from app.extensions import socketio
from app.utils.file_uploads import save_upload

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
    
    # Get campus-scoped offices for filter dropdown (fallback to session campus)
    campus_id = student.campus_id or session.get('selected_campus_id')
    offices = Office.query.filter_by(campus_id=campus_id).all() if campus_id else Office.query.all()
    
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
    # Enforce campus scope (fallback to session campus)
    campus_id = student.campus_id or session.get('selected_campus_id')
    if campus_id and office.campus_id != campus_id:
        flash('You can only submit inquiries to offices in your campus.', 'error')
        return redirect(url_for('student.university_offices'))
    
    # Get concern types for this office limited to inquiry usage (exclude counseling-only)
    concern_types = (
        ConcernType.query.join(OfficeConcernType)
        .filter(
            OfficeConcernType.office_id == office_id,
            OfficeConcernType.for_inquiries.is_(True)
        )
        .order_by(ConcernType.name)
        .all()
    )
    
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

        # Server-side word limit enforcement (keep in sync with template)
        def count_words(txt: str) -> int:
            if not txt:
                return 0
            return len([w for w in txt.replace('\n', ' ').strip().split() if w])

        SUBJECT_MAX_WORDS = 15
        MESSAGE_MAX_WORDS = 300
        subject_words = count_words(subject)
        message_words = count_words(message)
        if subject_words > SUBJECT_MAX_WORDS:
            flash(f'Subject exceeds the maximum of {SUBJECT_MAX_WORDS} words (current: {subject_words}).', 'error')
            return redirect(url_for('student.submit_inquiry', office_id=office_id))
        if message_words > MESSAGE_MAX_WORDS:
            flash(f'Message exceeds the maximum of {MESSAGE_MAX_WORDS} words (current: {message_words}).', 'error')
            return redirect(url_for('student.submit_inquiry', office_id=office_id))

        # Validate required fields
        if not office_id or not subject or not message:
            flash('Please fill all required fields', 'error')
            return redirect(url_for('student.inquiries'))

        # Ensure office_id is valid
        office = Office.query.get(office_id)
        if not office:
            flash('Selected office does not exist.', 'error')
            return redirect(url_for('student.inquiries'))

        # Get the student record and resolve campus
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        campus_id = student.campus_id or session.get('selected_campus_id')
        # Ensure office is in the same campus as the student
        if campus_id and office.campus_id != campus_id:
            flash('You can only submit inquiries to offices in your campus.', 'error')
            return redirect(url_for('student.inquiries'))

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
            status='sent',
            created_at=datetime.utcnow(),
            delivered_at=datetime.utcnow()
        )
        db.session.add(initial_message)
        db.session.flush()  # Flush to get message ID

        # Add concern type if provided
        if concern_type_id:
            # Validate that the concern type is supported by this office for inquiries (not just counseling)
            assoc = OfficeConcernType.query.filter_by(
                office_id=int(office_id),
                concern_type_id=int(concern_type_id),
                for_inquiries=True
            ).first()
            concern_type = ConcernType.query.get(concern_type_id)
            if not assoc or not concern_type:
                flash('Selected concern type is not available for inquiries in this office.', 'error')
                db.session.rollback()
                return redirect(url_for('student.submit_inquiry', office_id=office_id))
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
                    # Use centralized save_upload utility (fixes hardcoded path & size computation)
                    try:
                        static_path, meta = save_upload(file, subfolder='inquiries')
                    except Exception as fe:
                        # Skip invalid file silently to avoid breaking entire inquiry creation
                        continue

                    # Persist inquiry-level attachment (historical / counts)
                    inquiry_attachment = InquiryAttachment(
                        filename=meta.get('filename') or secure_filename(file.filename),
                        file_path=static_path,
                        file_size=meta.get('file_size'),
                        file_type=meta.get('file_type') or (file.content_type if hasattr(file, 'content_type') else None),
                        uploaded_by_id=current_user.id,
                        uploaded_at=datetime.utcnow(),
                        inquiry_id=new_inquiry.id
                    )
                    db.session.add(inquiry_attachment)

                    # ALSO create a message-level attachment so it renders with the initial message bubble
                    try:
                        msg_attachment = MessageAttachment(
                            filename=inquiry_attachment.filename,
                            file_path=inquiry_attachment.file_path,
                            file_size=inquiry_attachment.file_size,
                            file_type=inquiry_attachment.file_type,
                            uploaded_by_id=inquiry_attachment.uploaded_by_id,
                            uploaded_at=inquiry_attachment.uploaded_at,
                            message_id=initial_message.id
                        )
                        db.session.add(msg_attachment)
                    except Exception:
                        # If this fails we still keep the inquiry attachment; just continue
                        pass

        # Log this activity
        log_entry = StudentActivityLog.log_action(
            student=student,
            action="Created new inquiry",
            related_id=new_inquiry.id,
            related_type="inquiry",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )

        # Create notifications for office admins using smart notification system
        from app.utils.smart_notifications import SmartNotificationManager
        office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(office_id)

        for admin_user_id in office_admin_user_ids:
            SmartNotificationManager.create_inquiry_notification(
                new_inquiry, admin_user_id, 'new_inquiry'
            )

        # Auto-reply on student's first message if office concern type has auto-reply enabled
        try:
            # Collect concern type ids associated with this inquiry
            concern_type_ids = [ic.concern_type_id for ic in InquiryConcern.query.filter_by(inquiry_id=new_inquiry.id).all()]
            if concern_type_ids:
                assoc = OfficeConcernType.query.filter(
                    OfficeConcernType.office_id == new_inquiry.office_id,
                    OfficeConcernType.concern_type_id.in_(concern_type_ids),
                    OfficeConcernType.auto_reply_enabled.is_(True),
                    OfficeConcernType.auto_reply_message.isnot(None)
                ).order_by(OfficeConcernType.id.asc()).first()
            else:
                assoc = None

            if assoc and assoc.auto_reply_message and assoc.auto_reply_message.strip():
                # Choose an office admin as the sender
                office_admin = OfficeAdmin.query.filter_by(office_id=new_inquiry.office_id).first()
                if office_admin:
                    # Render placeholders
                    student_user = User.query.get(student.user_id)
                    rendered = assoc.auto_reply_message
                    try:
                        rendered = (
                            rendered
                            .replace('{{student_name}}', student_user.get_full_name() if student_user else 'Student')
                            .replace('{{office_name}}', office.name if office else 'Office')
                        )
                    except Exception:
                        pass

                    # Create the auto-reply message from office admin
                    auto_msg = InquiryMessage(
                        inquiry_id=new_inquiry.id,
                        sender_id=office_admin.user_id,
                        content=rendered,
                        status='sent',
                        delivered_at=datetime.utcnow(),
                        created_at=datetime.utcnow()
                    )
                    db.session.add(auto_msg)

                    # Notify the student about the office reply
                    db.session.add(Notification(
                        user_id=student.user_id,
                        title="New Office Reply",
                        message=f"New message from office in inquiry '{new_inquiry.subject}'",
                        is_read=False,
                        notification_type='inquiry_reply',
                        inquiry_id=new_inquiry.id,
                        source_office_id=new_inquiry.office_id
                    ))
        except Exception as e:
            # Do not fail creation due to auto-reply issues; log to console
            print(f"Auto-reply generation failed: {e}")

        db.session.commit()

        # Broadcast new inquiry to dashboard for real-time updates
        if broadcast_new_inquiry:
            try:
                broadcast_new_inquiry(new_inquiry)
            except Exception as e:
                # Log error but don't fail the inquiry creation
                print(f"Failed to broadcast new inquiry: {e}")

        # Emit to office namespace so office inquiries page & sidebar badge update in real-time
        try:
            payload = {
                'id': new_inquiry.id,
                'subject': new_inquiry.subject,
                'status': new_inquiry.status,
                'student_name': current_user.get_full_name() if hasattr(current_user, 'get_full_name') else 'Student',
                'office_id': new_inquiry.office_id,
                'created_at': new_inquiry.created_at.isoformat(),
            }
            # Room naming consistent with office websocket join logic: office_{office_id}
            socketio.emit('new_office_inquiry', payload, room=f"office_{new_inquiry.office_id}", namespace='/office')
        except Exception as e:
            print(f"Socket emit new_office_inquiry failed: {e}")

        # Removed success flash for cleaner UX; user is redirected directly to the inquiry conversation
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
                    try:
                        static_path, meta = save_upload(file, subfolder='messages')
                    except Exception:
                        continue
                    from app.models import MessageAttachment
                    attachment = MessageAttachment(
                        filename=meta.get('filename') or secure_filename(file.filename),
                        file_path=static_path,
                        file_size=meta.get('file_size'),
                        file_type=meta.get('file_type') or (file.content_type if hasattr(file, 'content_type') else None),
                        uploaded_by_id=current_user.id,
                        uploaded_at=datetime.utcnow(),
                        message_id=new_message.id
                    )
                    db.session.add(attachment)
        
        # Create smart notifications for office admins
        from app.utils.smart_notifications import SmartNotificationManager
        office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(
            inquiry.office_id, exclude_user_id=current_user.id
        )
        
        for admin_user_id in office_admin_user_ids:
            SmartNotificationManager.create_inquiry_notification(
                inquiry, admin_user_id, 'new_message'
            )
        
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
            is_student = sender.id == current_user.id if sender else False
            # serialize attachments if present
            atts = []
            try:
                for a in (message.attachments or []):
                    atts.append({
                        'filename': getattr(a, 'filename', None),
                        'file_path': getattr(a, 'file_path', None),
                        'file_type': getattr(a, 'file_type', None),
                        'file_size': getattr(a, 'file_size', None)
                    })
            except Exception:
                atts = []

            messages_data.append({
                'id': message.id,
                'content': message.content,
                'timestamp': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender_name': sender.get_full_name() if sender else 'Unknown',
                'is_student': is_student,
                'status': message.status,
                'attachments': atts
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


@student_bp.route('/api/inquiry/<int:inquiry_id>/send-message', methods=['POST'])
@login_required
@role_required(['student'])
def api_send_message(inquiry_id):
    """Send a chat message with optional attachments (student). Returns JSON and broadcasts via websocket."""
    try:
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        inquiry = Inquiry.query.filter_by(id=inquiry_id, student_id=student.id).first_or_404()

        content = (request.form.get('message') or '').strip()
        files = request.files.getlist('attachments') if 'attachments' in request.files else []

        if not content and not any(f.filename for f in files):
            return jsonify({'success': False, 'message': 'Message or attachment required'}), 400

        # Create message
        new_message = InquiryMessage(
            inquiry_id=inquiry.id,
            sender_id=current_user.id,
            content=content or '',
            status='sent',
            delivered_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.flush()  # get id

        attachments_payload = []
        # Save attachments
        for file in files:
            if not file or not file.filename:
                continue
            try:
                static_path, meta = save_upload(file, subfolder='messages')
            except Exception as fe:
                # Skip invalid files but continue processing others
                continue
            att = MessageAttachment(
                filename=meta.get('filename'),
                file_path=static_path,
                file_size=meta.get('file_size'),
                file_type=meta.get('file_type'),
                uploaded_by_id=current_user.id,
                uploaded_at=datetime.utcnow(),
                message_id=new_message.id
            )
            db.session.add(att)
            attachments_payload.append({
                'filename': att.filename,
                'file_path': att.file_path,
                'file_type': att.file_type,
                'file_size': att.file_size
            })

        # Notify office admins
        office = Office.query.get(inquiry.office_id)
        office_admins = OfficeAdmin.query.filter_by(office_id=office.id).all()
        for admin in office_admins:
            db.session.add(Notification(
                user_id=admin.user_id,
                title='New Message',
                message=f"New message from {current_user.get_full_name()} in inquiry '{inquiry.subject}'",
                is_read=False,
                notification_type='inquiry_reply',
                inquiry_id=inquiry.id,
                source_office_id=office.id
            ))

        db.session.commit()

        # Broadcast to room
        sender = User.query.get(current_user.id)
        payload = {
            'id': new_message.id,
            'content': new_message.content,
            'attachments': attachments_payload,
            'sender_id': current_user.id,
            'sender_name': sender.get_full_name() if sender else 'Student',
            'sender_role': 'student',
            'timestamp': new_message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_current_user': True,
            'status': new_message.status
        }
        room = f'inquiry_{inquiry.id}'
        socketio.emit('receive_message', payload, room=room, namespace='/chat')

        return jsonify({'success': True, 'message_id': new_message.id, 'message': payload})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500