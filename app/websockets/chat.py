from flask_socketio import emit, join_room, leave_room, disconnect
from flask import request, session, url_for
from flask_login import current_user
from app.extensions import socketio, db
from app.models import User, InquiryMessage, Inquiry, Student, Office, OfficeAdmin, Notification, InquiryConcern, OfficeConcernType
from datetime import datetime

def _extract_inquiry_id(data) -> int | None:
    """Best-effort extraction of inquiry_id from incoming event payloads.

    Accepts common variants and coerces to int when possible. Returns None if missing/invalid.
    """
    try:
        payload = data if isinstance(data, dict) else {}
        for key in ('inquiry_id', 'inquiryId', 'id', 'inquiry'):
            if key in payload:
                val = payload.get(key)
                if val in (None, ""):
                    continue
                try:
                    return int(val)
                except (TypeError, ValueError):
                    # Ignore unparsable values and keep looking
                    pass
        # Fallback: sometimes passed via query string (rare)
        if request is not None:
            q = request.args.get('inquiry_id')
            if q:
                try:
                    return int(q)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return None

def _avatar_url_for_user(user) -> str | None:
    """Build a cache-busted static URL for a user's profile picture, or None."""
    try:
        if not user:
            return None
        path = getattr(user, 'profile_pic_path', None) or (user.get_profile_pic_path() if hasattr(user, 'get_profile_pic_path') else None)
        if not path:
            return None
        base = url_for('static', filename=path)
        ver = getattr(user, 'profile_pic', None)
        return f"{base}?v={ver}" if ver else base
    except Exception:
        return None

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
    
    inquiry_id = _extract_inquiry_id(data)
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

    # On join, proactively mark all unread messages (from the other party) as read
    try:
        # Find unread messages in this inquiry not sent by the current user
        unread_messages = InquiryMessage.query.filter(
            InquiryMessage.inquiry_id == inquiry_id,
            InquiryMessage.sender_id != current_user.id,
            InquiryMessage.read_at.is_(None)
        ).all()

        read_count = 0
        now = datetime.utcnow()
        for msg in unread_messages:
            msg.read_at = now
            msg.status = 'read'
            read_count += 1

        if read_count > 0:
            # Mark related unread notifications for this user and inquiry as read
            try:
                related_notifications = Notification.query.filter(
                    Notification.user_id == current_user.id,
                    Notification.inquiry_id == inquiry_id,
                    Notification.is_read.is_(False),
                    Notification.notification_type == 'inquiry_reply'
                ).all()
                badge_count = 0
                for n in related_notifications:
                    n.is_read = True
                    badge_count += 1
            except Exception:
                badge_count = 0

            db.session.commit()

            # Emit read receipt for each message to the room with timestamp
            for msg in unread_messages:
                emit('message_read', {
                    'message_id': msg.id,
                    'inquiry_id': inquiry_id,
                    'read_at': (msg.read_at.isoformat() if msg.read_at else None)
                }, room=room)

            # Update notification badges for the reader side
            try:
                if badge_count > 0:
                    if getattr(current_user, 'role', None) == 'student':
                        socketio.emit('notification_update', {
                            'action': 'mark_as_read',
                            'inquiry_id': inquiry_id,
                            'count': badge_count
                        }, room=f'student_{current_user.id}', namespace='/')
                    elif getattr(current_user, 'role', None) == 'office_admin':
                        socketio.emit('office_notification_update', {
                            'action': 'mark_as_read',
                            'inquiry_id': inquiry_id,
                            'count': badge_count
                        }, room=f'user_{current_user.id}', namespace='/office')
            except Exception:
                pass
    except Exception as e:
        # Do not break join flow if marking read fails
        print(f"Error marking messages as read on join: {e}")

@socketio.on('leave_inquiry_room', namespace='/chat')
def handle_leave_room(data):
    """Handle a user leaving an inquiry chat room"""
    inquiry_id = _extract_inquiry_id(data)
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
    
    inquiry_id = _extract_inquiry_id(data)
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

    # Block sending if inquiry is closed
    try:
        if getattr(inquiry, 'status', '').lower() == 'closed':
            emit('error', {'message': 'This inquiry is closed. Further messages are disabled.'})
            return
    except Exception:
        pass
    
    try:
        # Determine if this is the student's first message in this inquiry
        is_first_student_message = False
        if current_user.role == 'student':
            pre_count = db.session.query(InquiryMessage).filter_by(inquiry_id=inquiry_id).count()
            is_first_student_message = (pre_count == 0)

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
        # Prepare attachments list (if any were eagerly loaded via relationship defaults)
        atts = []
        try:
            for a in (new_message.attachments or []):
                atts.append({
                    'filename': getattr(a, 'filename', None),
                    'file_path': getattr(a, 'file_path', None),
                    'file_type': getattr(a, 'file_type', None),
                    'file_size': getattr(a, 'file_size', None)
                })
        except Exception:
            atts = []

        message_data = {
            'id': new_message.id,
            'content': new_message.content,
            'attachments': atts,
            'sender_id': current_user.id,
            'sender_name': sender.get_full_name(),
            'sender_role': current_user.role,
            'sender_avatar_url': _avatar_url_for_user(sender),
            'timestamp': new_message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_current_user': True,  # This will be false for receivers
            'status': new_message.status
        }

        # Emit the message to all users in the room
        emit('receive_message', message_data, room=room)

        # Emit success to the sender
        emit('message_sent', {'success': True, 'message_id': new_message.id})

        # Auto-reply on first student message for enabled concern type
        if is_first_student_message:
            # Find any matching enabled auto-reply for this office's concern types on the inquiry
            concern_type_ids = [ic.concern_type_id for ic in InquiryConcern.query.filter_by(inquiry_id=inquiry_id).all()]
            if concern_type_ids:
                assoc = OfficeConcernType.query.filter(
                    OfficeConcernType.office_id == inquiry.office_id,
                    OfficeConcernType.concern_type_id.in_(concern_type_ids),
                    OfficeConcernType.auto_reply_enabled.is_(True),
                    OfficeConcernType.auto_reply_message.isnot(None)
                ).order_by(OfficeConcernType.id.asc()).first()
            else:
                assoc = None

            if assoc and assoc.auto_reply_message and assoc.auto_reply_message.strip():
                # Pick an office admin to be the sender
                office_admin = OfficeAdmin.query.filter_by(office_id=inquiry.office_id).first()
                if office_admin:
                    # Render placeholders
                    student_user = User.query.get(inquiry.student.user_id)
                    office = Office.query.get(inquiry.office_id)
                    rendered = assoc.auto_reply_message
                    try:
                        rendered = (
                            rendered
                            .replace('{{student_name}}', student_user.get_full_name() if student_user else 'Student')
                            .replace('{{office_name}}', office.name if office else 'Office')
                        )
                    except Exception:
                        pass

                    # Create office auto-reply message
                    auto_msg = InquiryMessage(
                        inquiry_id=inquiry_id,
                        sender_id=office_admin.user_id,
                        content=rendered,
                        status='sent',
                        delivered_at=datetime.utcnow()
                    )
                    db.session.add(auto_msg)
                    db.session.commit()

                    # Emit auto-reply to room
                    office_sender = User.query.get(office_admin.user_id)
                    auto_data = {
                        'id': auto_msg.id,
                        'content': auto_msg.content,
                        'sender_id': office_sender.id if office_sender else None,
                        'sender_name': office_sender.get_full_name() if office_sender else (office.name if office else 'Office'),
                        'sender_role': 'office_admin',
                        'sender_avatar_url': _avatar_url_for_user(office_sender) if office_sender else None,
                        'timestamp': auto_msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'is_current_user': False,
                        'status': auto_msg.status
                    }
                    emit('receive_message', auto_data, room=room)

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
        # Also mark any related unread notifications for this user and inquiry as read
        try:
            from app.models import Notification  # local import to avoid circulars
            related_notifications = Notification.query.filter(
                Notification.user_id == current_user.id,
                Notification.inquiry_id == message.inquiry_id,
                Notification.is_read.is_(False),
                Notification.notification_type == 'inquiry_reply'
            ).all()
            read_count = 0
            for n in related_notifications:
                n.is_read = True
                read_count += 1
        except Exception:
            read_count = 0

        db.session.commit()
        
        # Notify the sender that their message has been read
        room = f"inquiry_{message.inquiry_id}"
        emit('message_read', {
            'message_id': message_id,
            'inquiry_id': message.inquiry_id,
            'read_at': (message.read_at.isoformat() if message.read_at else None)
        }, room=room)

        # Push a real-time notification update to adjust badges on the reader side (current user)
        try:
            if read_count > 0:
                # Student namespace (default) vs office namespace
                if getattr(current_user, 'role', None) == 'student':
                    # Notify student's own room on default namespace
                    socketio.emit('notification_update', {
                        'action': 'mark_as_read',
                        'inquiry_id': message.inquiry_id,
                        'count': read_count
                    }, room=f'student_{current_user.id}', namespace='/')
                elif getattr(current_user, 'role', None) == 'office_admin':
                    # Notify specific office admin user on /office namespace
                    socketio.emit('office_notification_update', {
                        'action': 'mark_as_read',
                        'inquiry_id': message.inquiry_id,
                        'count': read_count
                    }, room=f'user_{current_user.id}', namespace='/office')
                else:
                    # For super_admin or others, skip badge update
                    pass
        except Exception:
            pass

@socketio.on('typing', namespace='/chat')
def handle_typing(data):
    """Handle typing indicator events for an inquiry room"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    inquiry_id = _extract_inquiry_id(data)
    if not inquiry_id:
        emit('error', {'message': 'Inquiry ID is required'})
        return

    inquiry = Inquiry.query.get(inquiry_id)
    if not inquiry:
        emit('error', {'message': 'Inquiry not found'})
        return

    # Access check
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
        emit('error', {'message': 'Access denied to this inquiry'})
        return

    room = f"inquiry_{inquiry_id}"
    user = User.query.get(current_user.id)
    emit('typing', {
        'inquiry_id': inquiry_id,
        'user_id': current_user.id,
        'user_name': user.get_full_name() if user else 'User',
        'role': current_user.role
    }, room=room, include_self=False)

@socketio.on('stop_typing', namespace='/chat')
def handle_stop_typing(data):
    """Handle stop typing indicator for an inquiry room"""
    if not current_user.is_authenticated:
        return

    inquiry_id = _extract_inquiry_id(data)
    if not inquiry_id:
        return

    inquiry = Inquiry.query.get(inquiry_id)
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

    room = f"inquiry_{inquiry_id}"
    emit('stop_typing', {
        'inquiry_id': inquiry_id,
        'user_id': current_user.id
    }, room=room, include_self=False)


@socketio.on('student_resolution_response', namespace='/chat')
def handle_student_resolution_response(data):
    """Handle student's confirmation or rejection after office marks inquiry as resolved.

    Expects payload: { inquiry_id: int, confirmed: bool, message?: str }
    Broadcasts result to the inquiry room so office can act (e.g., close inquiry on confirm).
    """
    try:
        if not current_user.is_authenticated:
            emit('error', {'message': 'Authentication required'})
            return

        inquiry_id = _extract_inquiry_id(data)
        if not inquiry_id:
            emit('error', {'message': 'Inquiry ID is required'})
            return

        inquiry = Inquiry.query.get(inquiry_id)
        if not inquiry:
            emit('error', {'message': 'Inquiry not found'})
            return

        # Only the owning student can respond
        if current_user.role != 'student':
            emit('error', {'message': 'Only students can confirm resolution'})
            return
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student or inquiry.student_id != student.id:
            emit('error', {'message': 'Access denied'})
            return

        confirmed = bool(data.get('confirmed'))
        message = (data.get('message') or '').strip()
        room = f"inquiry_{inquiry_id}"

        user = User.query.get(current_user.id)
        payload = {
            'inquiry_id': inquiry_id,
            'student_id': current_user.id,
            'student_name': (user.get_full_name() if user else 'Student'),
            'confirmed': confirmed,
            'message': message,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Notify all participants in the inquiry room
        if confirmed:
            emit('resolution_confirmed', payload, room=room)
        else:
            emit('resolution_needs_clarification', payload, room=room)

        # Optional: create an office notification so staff who aren't on this page are informed
        try:
            office_admins = OfficeAdmin.query.filter_by(office_id=inquiry.office_id).all()
            note_msg = 'Student confirmed resolution' if confirmed else 'Student needs more clarification'
            for admin in office_admins:
                db.session.add(Notification(
                    user_id=admin.user_id,
                    title='Inquiry Resolution Feedback',
                    message=f"{note_msg} for inquiry '{inquiry.subject}'.",
                    notification_type='resolution_feedback',
                    inquiry_id=inquiry.id,
                    source_office_id=inquiry.office_id,
                    is_read=False
                ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Non-fatal if notification creation fails
            pass
    except Exception as e:
        emit('error', {'message': f'Failed to process response: {str(e)}'})