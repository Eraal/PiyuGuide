from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, ConcernType, OfficeConcernType,
    Notification, MessageAttachment
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import time
from sqlalchemy import func, case, desc, or_
from app.office import office_bp
from app.utils import role_required


def calculate_response_rate(office_id):
    """
    Calculate the response rate for inquiries in a specific office.
    Response rate is defined as the percentage of inquiries that have at least one response.
    
    Args:
        office_id: The ID of the office to calculate the response rate for
        
    Returns:
        int: The response rate as a percentage (0-100)
    """
    # Get all inquiries for this office
    total_inquiries = Inquiry.query.filter_by(office_id=office_id).count()
    
    if total_inquiries == 0:
        return 0  # Avoid division by zero
    
    # Count inquiries with responses (those that have at least one message from an office admin)
    inquiries_with_responses = db.session.query(func.count(func.distinct(Inquiry.id))).join(
        InquiryMessage, Inquiry.id == InquiryMessage.inquiry_id
    ).join(
        User, InquiryMessage.sender_id == User.id
    ).filter(
        Inquiry.office_id == office_id,
        User.role == 'office_admin'
    ).scalar()
    
    # Calculate the response rate as a percentage
    response_rate = round((inquiries_with_responses / total_inquiries) * 100)
    
    return response_rate


@office_bp.route('/office-inquiry')
@login_required
@role_required(['office_admin'])
def office_inquiries():
    """Handle the office inquiries page with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of inquiries per page
    
    # Get the current office admin's office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        flash("You are not assigned to any office.", "error")
        return redirect(url_for('main.index'))
    
    # Get only concern types associated with this office
    concern_types = ConcernType.query.join(OfficeConcernType).filter(
        OfficeConcernType.office_id == office_admin.office_id
    ).all()
    
    # Base query for inquiries from this office
    query = Inquiry.query.filter_by(office_id=office_admin.office_id)
    
    # Calculate the total count
    total_inquiries = query.count()
    
    # Get count of pending inquiries for navbar badge
    pending_inquiries_count = query.filter_by(status='pending').count()
    
    # Calculate count of upcoming sessions for navbar badge
    now = datetime.utcnow()
    upcoming_sessions_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_admin.office_id,
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).count()
    
    # Apply pagination
    pagination = query.order_by(Inquiry.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    inquiries = pagination.items

    unread_notifications_count = 0  # You might want to calculate this value appropriately

    notifications = []  # You might want to populate this list with actual notifications
    
    # Calculate statistics
    stats = {
        'total': total_inquiries,
        'pending': query.filter_by(status='pending').count(),
        'resolved': query.filter_by(status='resolved').count(),
        'response_rate': calculate_response_rate(office_admin.office_id)
    }
    
    # Log this activity
    AuditLog.log_action(
        actor=current_user,
        action="Viewed Inquiries List",
        target_type="inquiry",
        office=office_admin.office,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'office/office_inquiries.html',
        inquiries=inquiries,
        pagination=pagination,
        total_inquiries=total_inquiries,
        stats=stats,
        concern_types=concern_types,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        pending_inquiries_count=pending_inquiries_count,
        upcoming_sessions_count=upcoming_sessions_count
    )


@office_bp.route('/inquiry/<int:inquiry_id>')
@login_required
@role_required(['office_admin'])
def view_inquiry(inquiry_id):
    """View a specific inquiry with its messages and details"""
    # Get the current office admin's office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        flash("You are not assigned to any office.", "error")
        return redirect(url_for('main.index'))
    
    # Fetch the inquiry and verify it belongs to this office
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_admin.office_id).first_or_404()
    
    # Get latest 6 messages for this inquiry for initial load
    messages = InquiryMessage.query.filter_by(
        inquiry_id=inquiry.id
    ).order_by(desc(InquiryMessage.created_at)).limit(6).all()
    
    # Reverse the messages to display in chronological order
    messages = messages[::-1]
    
    # Get total message count for pagination
    total_messages = InquiryMessage.query.filter_by(inquiry_id=inquiry.id).count()
    
    # Get count of pending inquiries for navbar badge
    pending_inquiries_count = Inquiry.query.filter_by(
        office_id=office_admin.office_id,
        status='pending'
    ).count()
    
    # Calculate count of upcoming sessions for navbar badge
    now = datetime.utcnow()
    upcoming_sessions_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_admin.office_id,
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).count()
    
    # Get unread notifications count for navbar
    from app.models import Notification
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    AuditLog.log_action(
        actor=current_user,
        action="Viewed Inquiry Details",
        target_type="inquiry",
        inquiry=inquiry,
        office=office_admin.office,
        status=inquiry.status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'office/view_inquiry.html',
        inquiry=inquiry,
        messages=messages,
        total_messages=total_messages,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        pending_inquiries_count=pending_inquiries_count,
        upcoming_sessions_count=upcoming_sessions_count,
        has_more_messages=(total_messages > 6)
    )


@office_bp.route('/update-inquiry-status', methods=['POST'])
@login_required
@role_required(['office_admin'])
def update_inquiry_status():
    """Update the status of an inquiry"""
    inquiry_id = request.form.get('inquiry_id')
    new_status = request.form.get('status')
    note = request.form.get('note')
    
    if not inquiry_id or not new_status:
        return jsonify({'success': False, 'message': 'Missing required parameters'})
    
    # Get the current office admin's office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        return jsonify({'success': False, 'message': 'Office admin not found'})
    
    # Fetch the inquiry and verify it belongs to this office
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_admin.office_id).first()
    if not inquiry:
        return jsonify({'success': False, 'message': 'Inquiry not found or access denied'})
    
    # Store old status for logging
    old_status = inquiry.status
    
    # Update status
    inquiry.status = new_status
    
    # Add status change message if note is provided
    if note:
        status_message = InquiryMessage(
            inquiry_id=inquiry.id,
            sender_id=current_user.id,
            content=f"Status changed to '{new_status}'. Note: {note}",
            status='sent',
            delivered_at=datetime.utcnow(),
            read_at=None
        )
        db.session.add(status_message)
    
    # Create notification for student
    from app.models import Notification
    notification = Notification(
        user_id=inquiry.student.user_id,
        title=f"Inquiry Status Updated",
        message=f"Your inquiry '{inquiry.subject}' status has been updated to {new_status}.",
        is_read=False
    )
    db.session.add(notification)
    
    # Log this activity
    AuditLog.log_action(
        actor=current_user,
        action=f"Updated Inquiry Status from {old_status} to {new_status}",
        target_type="inquiry",
        inquiry=inquiry,
        office=office_admin.office,
        status=new_status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    try:
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'Inquiry status updated to {new_status}',
            'new_status': new_status
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})


@office_bp.route('/delete-inquiry/<int:inquiry_id>', methods=['POST'])
@login_required
@role_required(['office_admin'])
def delete_inquiry(inquiry_id):
    """Delete an inquiry"""
    # Get the current office admin's office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        return jsonify({'success': False, 'message': 'Office admin not found'})
    
    # Fetch the inquiry and verify it belongs to this office
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_admin.office_id).first()
    if not inquiry:
        return jsonify({'success': False, 'message': 'Inquiry not found or access denied'})
    
    # Log this activity before deletion
    AuditLog.log_action(
        actor=current_user,
        action="Deleted Inquiry",
        target_type="inquiry",
        inquiry=inquiry,
        office=office_admin.office,
        status=inquiry.status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    # Store student user ID for notification
    student_user_id = inquiry.student.user_id
    inquiry_subject = inquiry.subject
    
    try:
        # Delete the inquiry
        db.session.delete(inquiry)
        
        # Create notification for student
        from app.models import Notification
        notification = Notification(
            user_id=student_user_id,
            title="Inquiry Deleted",
            message=f"Your inquiry '{inquiry_subject}' has been deleted by the office.",
            is_read=False
        )
        db.session.add(notification)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Inquiry deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})


@office_bp.route('/reply-to-inquiry/<int:inquiry_id>', methods=['POST'])
@login_required
@role_required(['office_admin'])
def reply_to_inquiry(inquiry_id):
    """Handle office admin replies to inquiries"""
    # Get the current office admin's office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Office admin not found'}), 403
        flash("You are not assigned to any office.", "error")
        return redirect(url_for('main.index'))
    
    # Fetch the inquiry and verify it belongs to this office
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_admin.office_id).first()
    if not inquiry:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Inquiry not found or access denied'}), 404
        flash("Inquiry not found or access denied.", "error")
        return redirect(url_for('office.office_inquiries'))
    
    # Get the message content from form submission
    message_content = request.form.get('message')
    if not message_content or message_content.strip() == '':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400
        flash("Message cannot be empty.", "error")
        return redirect(url_for('office.view_inquiry', inquiry_id=inquiry_id))
    
    # Create a new message with status tracking
    new_message = InquiryMessage(
        inquiry_id=inquiry_id,
        sender_id=current_user.id,
        content=message_content,
        status='sent',
        delivered_at=datetime.utcnow()
    )
    db.session.add(new_message)
    db.session.flush()  # Get ID for attachments
    
    # Handle file attachments if any
    file_paths = []
    if 'attachments' in request.files:
        files = request.files.getlist('attachments')
        for file in files:
            if file and file.filename:
                from app.utils import save_attachment
                file_path = save_attachment(file, 'messages')
                if file_path:
                    attachment = MessageAttachment(
                        filename=file.filename,
                        file_path=file_path,
                        file_size=file.content_length if hasattr(file, 'content_length') else 0,
                        file_type=file.content_type if hasattr(file, 'content_type') else None,
                        uploaded_by_id=current_user.id,
                        uploaded_at=datetime.utcnow(),
                        message_id=new_message.id
                    )
                    db.session.add(attachment)
                    file_paths.append(file_path)
    
    # Create notification for student
    notification = Notification(
        user_id=inquiry.student.user_id,
        title="New Office Reply",
        message=f"Office admin has replied to your inquiry '{inquiry.subject}'",
        is_read=False
    )
    db.session.add(notification)
    
    # Update inquiry status to in_progress if it's currently pending
    if inquiry.status == 'pending':
        inquiry.status = 'in_progress'
    
    # Log this activity
    AuditLog.log_action(
        actor=current_user,
        action="Replied to Inquiry",
        target_type="inquiry",
        inquiry=inquiry,
        office=office_admin.office,
        status=inquiry.status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    try:
        db.session.commit()
        
            
        # If it's an AJAX request, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True, 
                'message': 'Reply sent successfully',
                'message_id': new_message.id
            })
            
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Error sending reply: {str(e)}'}), 500
        flash(f"Error sending reply: {str(e)}", "error")
        return redirect(url_for('office.view_inquiry', inquiry_id=inquiry_id))
    
    # If not an AJAX request, redirect (fallback for traditional form submission)
    return redirect(url_for('office.view_inquiry', inquiry_id=inquiry_id))


@office_bp.route('/api/inquiry/<int:inquiry_id>/messages', methods=['GET'])
@login_required
@role_required(['office_admin'])
def get_older_messages(inquiry_id):
    """API to fetch older messages for infinite scrolling in chat view"""
    try:
        # Get the current office admin's office
        office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
        if not office_admin:
            return jsonify({'success': False, 'message': 'Office admin not found'}), 403
        
        # Fetch the inquiry and verify it belongs to this office
        inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_admin.office_id).first()
        if not inquiry:
            return jsonify({'success': False, 'message': 'Inquiry not found or access denied'}), 404
        
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
        
        # Mark any unread messages as read
        for message in messages:
            if message.sender_id != current_user.id and not message.read_at:
                message.read_at = datetime.utcnow()
        
        db.session.commit()
        
        # Serialize messages data for JSON response
        messages_data = []
        for message in messages:
            sender = User.query.get(message.sender_id)
            is_student = sender and sender.role == 'student'
            
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