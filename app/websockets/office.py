from flask_socketio import emit, join_room, leave_room, disconnect
from flask_login import current_user
from app.extensions import socketio


@socketio.on('connect', namespace='/office')
def office_connect():
    """Handle connection to office notifications namespace.

    Office admins join rooms:
      - office_{office_id}: for office-wide notifications
      - user_{user_id}: for user-targeted notifications
    """
    try:
        if not getattr(current_user, 'is_authenticated', False):
            disconnect()
            return False

        # Only office admins are allowed in this namespace
        if getattr(current_user, 'role', None) != 'office_admin':
            disconnect()
            return False

        office_admin = getattr(current_user, 'office_admin', None)
        if not office_admin:
            disconnect()
            return False

        office_room = f"office_{office_admin.office_id}"
        user_room = f"user_{current_user.id}"
        join_room(office_room, namespace='/office')
        join_room(user_room, namespace='/office')

        emit('connected', {
            'status': 'ok',
            'user_id': current_user.id,
            'office_id': office_admin.office_id
        })
    except Exception:
        # On any error, ensure disconnect to avoid leaking connections
        disconnect()
        return False


@socketio.on('disconnect', namespace='/office')
def office_disconnect():
    """Handle clean disconnects. Rooms are auto-managed by Flask-SocketIO."""
    # No-op; rooms are left automatically
    return


def push_office_notification_to_office(office_id: int, payload: dict):
    """Emit a live office notification to all users in an office room."""
    try:
        socketio.emit('office_notification', payload, room=f'office_{office_id}', namespace='/office')
    except Exception:
        # Avoid raising in emit helpers
        pass


def push_office_notification_to_user(user_id: int, payload: dict):
    """Emit a live office notification to a specific office admin user room."""
    try:
        socketio.emit('office_notification', payload, room=f'user_{user_id}', namespace='/office')
    except Exception:
        pass


def push_office_notification_broadcast(payload: dict):
    """Broadcast an office notification to all connected office admins.

    This emits to the '/office' namespace without a specific room,
    which delivers the event to all clients connected under that namespace.
    Useful for campus-wide public announcements.
    """
    try:
        socketio.emit('office_notification', payload, namespace='/office')
    except Exception:
        # Do not raise to avoid breaking the caller flow
        pass
