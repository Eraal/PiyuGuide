from flask_socketio import emit, join_room, disconnect
from flask_login import current_user
from app.extensions import socketio


@socketio.on('connect', namespace='/campus-admin')
def campus_admin_connect():
    """Handle websocket connection for campus admin (super_admin role) users.

    Rooms used:
      campus_<campus_id>  -> campus-wide announcements (public or office-targeted within campus)
      user_<user_id>      -> user-targeted (future use)
    """
    try:
        if not getattr(current_user, 'is_authenticated', False):
            disconnect()
            return False

        # Campus admins are users with role 'super_admin'
        if getattr(current_user, 'role', None) != 'super_admin':
            disconnect()
            return False

        campus_id = getattr(current_user, 'campus_id', None)
        if not campus_id:
            # No campus assigned – don't allow persistent connection
            disconnect()
            return False

        join_room(f"campus_{campus_id}", namespace='/campus-admin')
        join_room(f"user_{current_user.id}", namespace='/campus-admin')

        emit('connected', {
            'status': 'ok',
            'user_id': current_user.id,
            'campus_id': campus_id
        })
    except Exception:
        disconnect()
        return False


@socketio.on('disconnect', namespace='/campus-admin')
def campus_admin_disconnect():
    # Rooms auto-handled by Flask-SocketIO; nothing required here.
    return


def push_campus_admin_announcement(campus_id: int, payload: dict):
    """Emit a real-time notification to all campus admin users of a campus.

    Currently used for announcements (payload.kind == 'announcement'). Designed to be
    extensible for other kinds (e.g., 'system', 'inquiry', 'event').
    """
    try:
        socketio.emit('campus_announcement', payload, room=f'campus_{campus_id}', namespace='/campus-admin')
    except Exception:
        pass
