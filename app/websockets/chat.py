from flask_socketio import emit, join_room, leave_room, disconnect
from flask import request, session
from flask_login import current_user
from app.extensions import socketio, db
from app.models import User, InquiryMessage, Inquiry, Student, Office, OfficeAdmin, Notification
from datetime import datetime

@socketio.on('connect', namespace='/chat')
def handle_connect():
    """Handle connection to chat namespace"""
    if not current_user.is_authenticated:
        # Disconnect non-authenticated users
        disconnect()
        return False
    
    # User is authenticated, log connection
    print(f"User {current_user.id} ({current_user.role}) connected to chat")
    emit('connect_response', {'status': 'connected', 'user_id': current_user.id, 'role': current_user.role})

@socketio.on('disconnect', namespace='/chat')
def handle_disconnect():
    """Handle disconnection from chat namespace"""
    if current_user.is_authenticated:
        print(f"User {current_user.id} disconnected from chat")

@socketio.on('join_inquiry_room', namespace='/chat')
def handle_join_room(data):
    """Handle a user joining an inquiry chat room"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return
    
    inquiry_id = data.get('inquiry_id')
    if not inquiry_id:
        emit('error', {'message': 'Inquiry ID is required'})
        return
    
    # Generate room name from inquiry ID
    room = f"inquiry_{inquiry_id}"
    
    # Verify user has access to this inquiry
    inquiry = Inquiry.query.get(inquiry_id)
    if not inquiry:
        emit('error', {'message': 'Inquiry not found'})
        return
    
    has_access = False
    
    # Check access based on user role
    if current_user.role == 'student':
        # Student should only access their own inquiries
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and inquiry.student_id == student.id:
            has_access = True
    elif current_user.role == 'office_admin':
        # Office admin should only access inquiries for their office
        office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
        if office_admin and inquiry.office_id == office_admin.office_id:
            has_access = True
    elif current_user.role == 'super_admin':
        # Super admin can access all inquiries
        has_access = True
    
    if not has_access:
        emit('error', {'message': 'Access denied to this inquiry'})
        return
    
    # Join the room
    join_room(room)
    print(f"User {current_user.id} joined room {room}")
    emit('room_joined', {'room': room, 'inquiry_id': inquiry_id}, room=room)

@socketio.on('leave_inquiry_room', namespace='/chat')
def handle_leave_room(data):
    """Handle a user leaving an inquiry chat room"""
    inquiry_id = data.get('inquiry_id')
    if not inquiry_id:
        return
    
    room = f"inquiry_{inquiry_id}"
    leave_room(room)
    print(f"User {current_user.id} left room {room}")
    emit('room_left', {'room': room, 'inquiry_id': inquiry_id})

@socketio.on('send_message', namespace='/chat')
def handle_send_message(data):
    """Handle sending a chat message"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return
    
    inquiry_id = data.get('inquiry_id')
    content = data.get('content')
    
    if not inquiry_id or not content or content.strip() == '':
        emit('error', {'message': 'Invalid message data'})
        return
    
    # Get the inquiry and verify user has access
    inquiry = Inquiry.query.get(inquiry_id)
    if not inquiry:
        emit('error', {'message': 'Inquiry not found'})
        return
    
    has_access = False
    
    # Check access based on user role
    if current_user.role == 'student':
        # Student should only access their own inquiries
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and inquiry.student_id == student.id:
            has_access = True
    elif current_user.role == 'office_admin':
        # Office admin should only access inquiries for their office
        office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
        if office_admin and inquiry.office_id == office_admin.office_id:
            has_access = True
    elif current_user.role == 'super_admin':
        # Super admin can access all inquiries
        has_access = True
    
    if not has_access:
        emit('error', {'message': 'Access denied to this inquiry'})
        return
    
    try:
        # Create a new message
        new_message = InquiryMessage(
            inquiry_id=inquiry_id,
            sender_id=current_user.id,
            content=content,
            status='sent',
            delivered_at=datetime.utcnow()
        )
        db.session.add(new_message)
        
        # If the sender is an office admin and the inquiry is in 'pending' status, update to 'in_progress'
        if current_user.role in ['office_admin', 'super_admin'] and inquiry.status == 'pending':
            inquiry.status = 'in_progress'
        
        db.session.commit()
        
        # Get the room for this inquiry
        room = f"inquiry_{inquiry_id}"
        
        # Create a notification for the recipient
        if current_user.role == 'student':
            # Message is from student to office, notify office admin(s)
            office = Office.query.get(inquiry.office_id)
            office_admins = OfficeAdmin.query.filter_by(office_id=office.id).all()
            
            for admin in office_admins:
                notification = Notification(
                    user_id=admin.user_id,
                    title="New Message",
                    message=f"New message from {current_user.get_full_name()} in inquiry '{inquiry.subject}'",
                    is_read=False,
                    notification_type='inquiry_reply',
                    inquiry_id=inquiry_id
                )
                db.session.add(notification)
        else:
            # Message is from office to student, notify student
            notification = Notification(
                user_id=inquiry.student.user_id,
                title="New Office Reply",
                message=f"New message from office in inquiry '{inquiry.subject}'",
                is_read=False,
                notification_type='inquiry_reply',
                inquiry_id=inquiry_id,
                source_office_id=inquiry.office_id
            )
            db.session.add(notification)
        
        db.session.commit()
        
        # Prepare message data for the frontend
        sender = User.query.get(current_user.id)
        message_data = {
            'id': new_message.id,
            'content': new_message.content,
            'sender_id': current_user.id,
            'sender_name': sender.get_full_name(),
            'sender_role': current_user.role,
            'timestamp': new_message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_current_user': True  # This will be false for receivers
        }
        
        # Emit the message to all users in the room
        emit('receive_message', message_data, room=room)
        
        # Emit success to the sender
        emit('message_sent', {'success': True, 'message_id': new_message.id})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sending message: {str(e)}")
        emit('error', {'message': f'Failed to send message: {str(e)}'})

@socketio.on('mark_as_read', namespace='/chat')
def handle_mark_as_read(data):
    """Mark a message as read"""
    if not current_user.is_authenticated:
        return
    
    message_id = data.get('message_id')
    if not message_id:
        return
    
    message = InquiryMessage.query.get(message_id)
    if not message or message.sender_id == current_user.id:
        return
    
    # Verify user has access to this message
    inquiry = Inquiry.query.get(message.inquiry_id)
    if not inquiry:
        return
    
    has_access = False
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and inquiry.student_id == student.id:
            has_access = True
    elif current_user.role == 'office_admin':
        office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
        if office_admin and inquiry.office_id == office_admin.office_id:
            has_access = True
    elif current_user.role == 'super_admin':
        has_access = True
    
    if not has_access:
        return
    
    # Mark the message as read if it hasn't been read yet
    if not message.read_at:
        message.read_at = datetime.utcnow()
        message.status = 'read'
        db.session.commit()
        
        # Notify the sender that their message has been read
        room = f"inquiry_{message.inquiry_id}"
        emit('message_read', {'message_id': message_id}, room=room) 