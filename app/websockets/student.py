from flask_socketio import emit, join_room, disconnect
from flask_login import current_user
from app.extensions import socketio

# Lazy imports guarded in functions to avoid circulars during app init
try:
    from app.models import db, Student, Inquiry
except Exception:  # pragma: no cover - during certain tooling phases
    db = None
    Student = None
    Inquiry = None


@socketio.on('connect')
def student_connect():
    """Handle connection for student clients on default namespace.

    Students are auto-joined to a user-specific room: student_{user_id}.
    Non-students are disconnected for this default student channel.
    """
    try:
        if not getattr(current_user, 'is_authenticated', False):
            disconnect()
            return False

        if getattr(current_user, 'role', None) != 'student':
            # Restrict default namespace to student-facing events
            disconnect()
            return False

        # Join personal room for targeted events and global student broadcast room
        join_room(f"student_{current_user.id}")
        join_room("student_room")

        # Also join rooms by offices the student has interacted with for targeted office announcements
        try:
            if Student and Inquiry:
                student = Student.query.filter_by(user_id=current_user.id).first()
                if student:
                    office_ids = (
                        Inquiry.query.with_entities(Inquiry.office_id)
                        .filter_by(student_id=student.id)
                        .distinct()
                        .all()
                    )
                    for (office_id,) in office_ids:
                        if office_id:
                            join_room(f"student_office_{office_id}")
        except Exception:
            # Non-fatal if DB isn't available or any error occurs
            pass

        emit('connected', {
            'status': 'ok',
            'user_id': current_user.id,
            'role': 'student'
        })
    except Exception:
        disconnect()
        return False


@socketio.on('join')
def student_join_room(data):
    """Allow student to join permissible rooms via client request.

    Only allows:
      - 'student_room' (broadcast to all students)
      - f'student_{current_user.id}' (their own room)
    """
    try:
        if not getattr(current_user, 'is_authenticated', False) or getattr(current_user, 'role', None) != 'student':
            disconnect()
            return False

        room = (data or {}).get('room')
        if not room:
            return

        allowed_rooms = { 'student_room', f'student_{current_user.id}' }
        if room in allowed_rooms:
            join_room(room)
    except Exception:
        # Silently ignore to avoid crashing the socket handler
        pass


@socketio.on('disconnect')
def student_disconnect():
    """Handle student disconnects (rooms auto-managed by Flask-SocketIO)."""
    return


def push_student_notification_to_user(user_id: int, payload: dict):
    """Emit a real-time student notification to a specific student user room.

    Args:
        user_id: Target student user ID
        payload: Dict payload to send. Should include at least 'title', 'message', and 'id'.
    """
    try:
        socketio.emit('new_notification', payload, room=f'student_{user_id}')
    except Exception:
        # Avoid raising in emit helpers; non-fatal if sockets unavailable
        pass


def push_student_announcement_public(payload: dict):
    """Broadcast a public announcement to all connected students.

    Uses the default namespace and the 'student_room' broadcast room.
    Payload should minimally include: title, message/content, announcement_id, notification_type='announcement'.
    """
    try:
        socketio.emit('new_notification', payload, room='student_room')
    except Exception:
        pass


def push_student_announcement_to_office(office_id: int, payload: dict):
    """Broadcast an office-targeted announcement to students who interacted with that office.

    Students are auto-joined to rooms named 'student_office_<office_id>' on connect based on inquiry history.
    """
    try:
        socketio.emit('new_notification', payload, room=f'student_office_{office_id}')
    except Exception:
        pass


def push_student_session_update(user_id: int, payload: dict):
    """Emit a real-time session update (status/time/etc.) to a specific student user room.

    Expects payload to include at least: session_id, status. Optional: scheduled_at, is_video_session, link.
    """
    try:
        socketio.emit('session_update', payload, room=f'student_{user_id}')
    except Exception:
        # Avoid raising in emit helpers; non-fatal if sockets unavailable
        pass
