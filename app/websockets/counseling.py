from flask_socketio import emit, join_room, leave_room, disconnect, rooms
from flask_login import current_user
from app.extensions import socketio, db
from app.models import CounselingSession, SessionParticipation, Student, User, OfficeAdmin
from datetime import datetime
import uuid
import logging
import json
from datetime import timedelta


# Configure logging
logger = logging.getLogger(__name__)

# Store active sessions and participants
active_sessions = {}
session_rooms = {}
user_sessions = {}  # Track which session each user is in

# Reconnection handling
DISCONNECT_GRACE_SECONDS = 45  # allow users to reconnect without being removed

def _schedule_disconnect_cleanup(session_id, user_id, name, role):
    """Schedule cleanup of a disconnected user after a grace period."""
    def task():
        try:
            socketio.sleep(DISCONNECT_GRACE_SECONDS)
            participant = active_sessions.get(session_id, {}).get(user_id)
            if participant and not participant.get('connected', True):
                # Remove and notify others only now
                room_name = f"video_session_{session_id}"
                try:
                    del active_sessions[session_id][user_id]
                    if not active_sessions[session_id]:
                        del active_sessions[session_id]
                except Exception:
                    pass
                emit('user_left', {
                    'user_id': user_id,
                    'name': name,
                    'role': role,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=room_name)
        except Exception:
            # Avoid crashing background task
            logger.exception('Error in disconnect cleanup task')
    socketio.start_background_task(task)

@socketio.on('connect', namespace='/video-counseling')
def handle_connect():
    """Handle client connection to video counseling namespace"""
    if not current_user.is_authenticated:
        logger.warning("Unauthorized connection attempt to video counseling")
        disconnect()
        return False
    
    logger.info(f"User {current_user.id} ({current_user.role}) connected to video counseling")
    emit('connection_status', {
        'status': 'connected',
        'user_id': current_user.id,
        'role': current_user.role,
        'timestamp': datetime.utcnow().isoformat()
    })

@socketio.on('disconnect', namespace='/video-counseling')
def handle_disconnect():
    """Handle client disconnection"""
    if current_user.is_authenticated:
        logger.info(f"User {current_user.id} disconnected from video counseling")
        # Mark as disconnected but keep for a grace period to allow reconnection
        for session_id, participants in list(active_sessions.items()):
            if current_user.id in participants:
                p = participants[current_user.id]
                p['connected'] = False
                p['disconnected_at'] = datetime.utcnow()
                # Schedule delayed cleanup
                _schedule_disconnect_cleanup(session_id, current_user.id, p.get('name'), p.get('role'))

@socketio.on('join_session', namespace='/video-counseling')
def handle_join_session(data):
    """Handle user joining a video session"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return
    
    session_id = data.get('session_id')
    if not session_id:
        emit('error', {'message': 'Session ID required'})
        return
    
    # Verify session exists and user has access
    session = CounselingSession.query.get(session_id)
    if not session:
        emit('error', {'message': 'Session not found'})
        return
    
    # Check user access to session
    has_access = False
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and session.student_id == student.id:
            has_access = True
    elif current_user.role in ['office_admin', 'super_admin']:
        if session.counselor_id == current_user.id or current_user.role == 'super_admin':
            has_access = True
    
    if not has_access:
        emit('error', {'message': 'Access denied to this session'})
        return
    
    # Generate room name
    room_name = f"video_session_{session_id}"
    
    # Join the room
    join_room(room_name)
    
    # Track user in session (preserve prior state if present)
    if session_id not in active_sessions:
        active_sessions[session_id] = {}

    existing = active_sessions[session_id].get(current_user.id)
    if existing:
        # Restore existing user state
        existing['connected'] = True
        existing['disconnected_at'] = None
        # Ensure name/role up to date
        existing['name'] = current_user.get_full_name()
        existing['role'] = current_user.role
        # Keep 'ready' and 'in_call' flags as-is
    else:
        active_sessions[session_id][current_user.id] = {
            'user_id': current_user.id,
            'role': current_user.role,
            'name': current_user.get_full_name(),
            'joined_at': datetime.utcnow(),
            'ready': False,
            'in_call': False,
            'connected': True,
            # Track initial media state for this participant (defaults true)
            'audio_enabled': True,
            'video_enabled': True
        }
    
    # Create participation record
    participation = SessionParticipation.query.filter_by(
        session_id=session_id,
        user_id=current_user.id
    ).first()
    
    if not participation:
        participation = SessionParticipation(
            session_id=session_id,
            user_id=current_user.id,
            joined_at=datetime.utcnow(),
            device_info=data.get('device_info', ''),
            ip_address=data.get('ip_address', '')
        )
        db.session.add(participation)
        db.session.commit()
    
    logger.info(f"User {current_user.id} joined session {session_id}")
    
    # Notify others in the room
    emit('user_joined', {
        'user_id': current_user.id,
        'role': current_user.role,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)
    
    # Send current participants to the newly joined user
    participants = []
    if session_id in active_sessions:
        for user_data in active_sessions[session_id].values():
            if user_data['user_id'] != current_user.id:
                participants.append({
                    'user_id': user_data['user_id'],
                    'role': user_data['role'],
                    'name': user_data['name'],
                    'ready': user_data['ready'],
                    'in_call': user_data.get('in_call', False),
                    'connected': user_data.get('connected', True),
                    'audio_enabled': user_data.get('audio_enabled', True),
                    'video_enabled': user_data.get('video_enabled', True)
                })
    
    emit('session_joined', {
        'session_id': session_id,
        'room': room_name,
        'participants': participants,
        'your_role': current_user.role,
        'started_at': session.started_at.isoformat() if getattr(session, 'started_at', None) else None,
        'ended_at': session.ended_at.isoformat() if getattr(session, 'ended_at', None) else None
    })
    
    # Check if both counselor and student are present
    check_session_ready(session_id, room_name)

    # If the user had an active call previously, notify peers to renegotiate
    participant_state = active_sessions[session_id].get(current_user.id, {})
    if participant_state.get('in_call'):
        emit('reconnect_request', {
            'user_id': current_user.id,
            'name': current_user.get_full_name(),
            'role': current_user.role,
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=room_name, include_self=False)

@socketio.on('ready', namespace='/video-counseling')
def handle_ready(data):
    """Handle user indicating they're ready for the call"""
    session_id = data.get('session_id')
    if not session_id or session_id not in active_sessions:
        emit('error', {'message': 'Invalid session'})
        return
    
    if current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    # Mark user as ready
    active_sessions[session_id][current_user.id]['ready'] = True
    
    room_name = f"video_session_{session_id}"
    
    # Notify others
    emit('user_ready', {
        'user_id': current_user.id,
        'role': current_user.role,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)
    
    logger.info(f"User {current_user.id} is ready in session {session_id}")
    
    # Check if call can start
    check_session_ready(session_id, room_name)

@socketio.on('not_ready', namespace='/video-counseling')
def handle_not_ready(data):
    """Handle user indicating they're not ready for the call"""
    session_id = data.get('session_id')
    if not session_id or session_id not in active_sessions:
        emit('error', {'message': 'Invalid session'})
        return
    
    if current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    # Mark user as not ready
    active_sessions[session_id][current_user.id]['ready'] = False
    
    room_name = f"video_session_{session_id}"
    
    # Notify others
    emit('user_not_ready', {
        'user_id': current_user.id,
        'role': current_user.role,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)
    
    logger.info(f"User {current_user.id} is not ready in session {session_id}")
    
    # Check session status
    check_session_ready(session_id, room_name)

@socketio.on('start_call', namespace='/video-counseling')
def handle_start_call(data):
    """Handle call start request (counselor initiates)"""
    if current_user.role not in ['office_admin', 'super_admin']:
        emit('error', {'message': 'Only counselors can start the call'})
        return
    
    session_id = data.get('session_id')
    if not session_id:
        emit('error', {'message': 'Session ID required'})
        return
    
    # Verify session exists and user has access
    session = CounselingSession.query.get(session_id)
    if not session or (session.counselor_id != current_user.id and current_user.role != 'super_admin'):
        emit('error', {'message': 'Access denied or session not found'})
        return
    
    # Check if session has participants
    if session_id not in active_sessions:
        emit('error', {'message': 'No participants in session'})
        return
    
    participants = active_sessions[session_id]
    has_student = any(p['role'] == 'student' for p in participants.values())
    has_counselor = any(p['role'] in ['office_admin', 'super_admin'] for p in participants.values())
    
    if not (has_student and has_counselor):
        emit('error', {'message': 'Both student and counselor must be present'})
        return
    
    room_name = f"video_session_{session_id}"
    
    # Ensure call is marked as started exactly once, without disrupting external status semantics
    try:
        if not session.started_at:
            session.started_at = datetime.utcnow()
        # Avoid forcing a specific status here to preserve compatibility with routes using 'in_progress'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating session start: {str(e)}")
    
    # Notify all participants that the call is starting
    emit('call_starting', {
        'session_id': session_id,
        'started_by': current_user.get_full_name(),
        'participants': [
            {
                'user_id': p['user_id'],
                'role': p['role'],
                'name': p['name']
            }
            for p in participants.values()
        ],
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name)
    
    logger.info(f"Call started by {current_user.id} for session {session_id}")

@socketio.on('join_call', namespace='/video-counseling')
def handle_join_call(data):
    """Handle user joining the active call"""
    session_id = data.get('session_id')
    if not session_id:
        emit('error', {'message': 'Session ID required'})
        return
    
    # Verify user is in session
    if session_id not in active_sessions or current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    room_name = f"video_session_{session_id}"
    
    # Mark user as joined in call
    active_sessions[session_id][current_user.id]['in_call'] = True
    active_sessions[session_id][current_user.id]['call_joined_at'] = datetime.utcnow()
    
    # Notify others that user has joined the call
    emit('user_joined_call', {
        'user_id': current_user.id,
        'role': current_user.role,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)
    
    # Send initial media state of other participants to the newly joined user
    try:
        other_states = []
        for participant in active_sessions[session_id].values():
            if participant['user_id'] == current_user.id:
                continue
            other_states.append({
                'user_id': participant['user_id'],
                'name': participant['name'],
                'audio_enabled': participant.get('audio_enabled', True),
                'video_enabled': participant.get('video_enabled', True)
            })
        emit('initial_media_state', {
            'session_id': session_id,
            'participants': other_states
        })
    except Exception:
        logger.exception('Failed to emit initial media state to joining user')

    # Broadcast the joining user's current media state to peers
    try:
        me = active_sessions[session_id].get(current_user.id, {})
        emit('user_audio_toggle', {
            'user_id': current_user.id,
            'audio_enabled': me.get('audio_enabled', True),
            'name': current_user.get_full_name()
        }, room=room_name, include_self=False)
        emit('user_video_toggle', {
            'user_id': current_user.id,
            'video_enabled': me.get('video_enabled', True),
            'name': current_user.get_full_name()
        }, room=room_name, include_self=False)
    except Exception:
        logger.exception('Failed to broadcast joining user media state')

    # Send call state to the newly joined user
    call_participants = []
    for participant in active_sessions[session_id].values():
        if participant.get('in_call', False):
            call_participants.append({
                'user_id': participant['user_id'],
                'role': participant['role'],
                'name': participant['name']
            })
    
    # Fetch authoritative started_at for timer base; set it if missing
    try:
        db_session = CounselingSession.query.get(session_id)
        if db_session and not db_session.started_at:
            db_session.started_at = datetime.utcnow()
            db.session.commit()
    except Exception:
        db.session.rollback()

    emit('call_joined', {
        'session_id': session_id,
        'participants': call_participants,
        'your_role': current_user.role,
        'started_at': (CounselingSession.query.get(session_id).started_at.isoformat()
                       if CounselingSession.query.get(session_id) and CounselingSession.query.get(session_id).started_at else None)
    })
    
    logger.info(f"User {current_user.id} joined call for session {session_id}")

@socketio.on('waiting_room_media_toggle', namespace='/video-counseling')
def handle_waiting_room_media_toggle(data):
    """Handle media toggle in waiting room"""
    session_id = data.get('session_id')
    media_type = data.get('media_type')  # 'audio' or 'video'
    enabled = data.get('enabled')
    
    if not all([session_id, media_type]):
        return
    
    room_name = f"video_session_{session_id}"
    
    # Persist waiting-room media state so newcomers can get initial state
    try:
        if session_id in active_sessions and current_user.id in active_sessions[session_id]:
            participant = active_sessions[session_id][current_user.id]
            if media_type == 'audio' and enabled is not None:
                participant['audio_enabled'] = bool(enabled)
            elif media_type == 'video' and enabled is not None:
                participant['video_enabled'] = bool(enabled)
    except Exception:
        logger.exception('Failed to persist waiting room media toggle')

    # Notify others in waiting room
    emit('waiting_room_media_update', {
        'user_id': current_user.id,
        'media_type': media_type,
        'enabled': enabled,
        'name': current_user.get_full_name()
    }, room=room_name, include_self=False)

@socketio.on('offer', namespace='/video-counseling')
def handle_offer(data):
    """Handle WebRTC offer"""
    session_id = data.get('session_id')
    offer = data.get('offer')
    target_user_id = data.get('target_user_id')
    
    if not session_id or not offer:
        emit('error', {'message': 'Missing required data for offer'})
        return
    
    # Verify user is in session
    if session_id not in active_sessions or current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    room_name = f"video_session_{session_id}"
    
    logger.info(f"Handling offer from {current_user.id} (role: {current_user.role}) in session {session_id}")
    
    # Generate a unique offer ID to prevent conflicts
    offer_id = str(uuid.uuid4())
    
    # Forward offer to all other users in room or specific target
    offer_data = {
        'session_id': session_id,
        'offer': offer,
        'offer_id': offer_id,
        'from_user_id': current_user.id,
        'from_role': current_user.role,
        'from_name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if target_user_id:
        offer_data['target_user_id'] = target_user_id
        logger.info(f"Sending targeted offer to user {target_user_id}")
    else:
        logger.info(f"Broadcasting offer to all participants in session")
    
    emit('offer_received', offer_data, room=room_name, include_self=False)
    
    logger.info(f"Offer {offer_id} sent from {current_user.id} to session {session_id}")

@socketio.on('answer', namespace='/video-counseling')
def handle_answer(data):
    """Handle WebRTC answer"""
    session_id = data.get('session_id')
    answer = data.get('answer')
    offer_id = data.get('offer_id')
    target_user_id = data.get('target_user_id')
    
    if not all([session_id, answer]):
        emit('error', {'message': 'Missing required data for answer'})
        return
    
    # Verify user is in session
    if session_id not in active_sessions or current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    room_name = f"video_session_{session_id}"
    
    logger.info(f"Handling answer from {current_user.id} (role: {current_user.role}) for offer {offer_id}")
    
    # Forward answer to all users in room or specific target
    answer_data = {
        'session_id': session_id,
        'answer': answer,
        'offer_id': offer_id,
        'from_user_id': current_user.id,
        'from_role': current_user.role,
        'from_name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if target_user_id:
        answer_data['target_user_id'] = target_user_id
        logger.info(f"Sending targeted answer to user {target_user_id}")
    else:
        logger.info(f"Broadcasting answer to all participants in session")
    
    emit('answer_received', answer_data, room=room_name, include_self=False)
    
    logger.info(f"Answer sent from {current_user.id} in session {session_id}")

@socketio.on('ice_candidate', namespace='/video-counseling')
def handle_ice_candidate(data):
    """Handle ICE candidate exchange"""
    session_id = data.get('session_id')
    candidate = data.get('candidate')
    target_user_id = data.get('target_user_id')
    
    if not all([session_id, candidate]):
        emit('error', {'message': 'Missing required data for ICE candidate'})
        return
    
    # Verify user is in session
    if session_id not in active_sessions or current_user.id not in active_sessions[session_id]:
        emit('error', {'message': 'User not in session'})
        return
    
    room_name = f"video_session_{session_id}"
    
    # Forward ICE candidate to other users
    candidate_data = {
        'session_id': session_id,
        'candidate': candidate,
        'from_user_id': current_user.id,
        'from_role': current_user.role,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if target_user_id:
        candidate_data['target_user_id'] = target_user_id
    
    emit('ice_candidate_received', candidate_data, room=room_name, include_self=False)
    
    logger.debug(f"ICE candidate sent from {current_user.id} in session {session_id}")

@socketio.on('toggle_audio', namespace='/video-counseling')
def handle_toggle_audio(data):
    """Handle audio toggle notification"""
    session_id = data.get('session_id')
    audio_enabled = data.get('audio_enabled')
    
    if session_id is None:
        return
    
    room_name = f"video_session_{session_id}"
    
    # Persist current participant audio state
    try:
        if session_id in active_sessions and current_user.id in active_sessions[session_id]:
            active_sessions[session_id][current_user.id]['audio_enabled'] = bool(audio_enabled)
    except Exception:
        logger.exception('Failed to persist audio toggle state')

    # Notify others of audio state change
    emit('user_audio_toggle', {
        'user_id': current_user.id,
        'audio_enabled': audio_enabled,
        'name': current_user.get_full_name()
    }, room=room_name, include_self=False)

@socketio.on('toggle_video', namespace='/video-counseling')
def handle_toggle_video(data):
    """Handle video toggle notification"""
    session_id = data.get('session_id')
    video_enabled = data.get('video_enabled')
    
    if session_id is None:
        return
    
    room_name = f"video_session_{session_id}"
    
    # Persist current participant video state
    try:
        if session_id in active_sessions and current_user.id in active_sessions[session_id]:
            active_sessions[session_id][current_user.id]['video_enabled'] = bool(video_enabled)
    except Exception:
        logger.exception('Failed to persist video toggle state')

    # Notify others of video state change
    emit('user_video_toggle', {
        'user_id': current_user.id,
        'video_enabled': video_enabled,
        'name': current_user.get_full_name()
    }, room=room_name, include_self=False)

# Recording features removed as per project requirements

@socketio.on('save_notes', namespace='/video-counseling')
def handle_save_notes(data):
    """Handle saving session notes (counselor only)"""
    if current_user.role not in ['office_admin', 'super_admin']:
        emit('error', {'message': 'Only counselors can save notes'})
        return
    
    session_id = data.get('session_id')
    notes = data.get('notes', '')
    
    if not session_id:
        emit('error', {'message': 'Session ID required'})
        return
    
    try:
        session = CounselingSession.query.get(session_id)
        if session and session.counselor_id == current_user.id:
            session.notes = notes
            db.session.commit()
            emit('notes_saved', {'success': True, 'timestamp': datetime.utcnow().isoformat()})
            logger.info(f"Notes saved by {current_user.id} for session {session_id}")
        else:
            emit('error', {'message': 'Access denied or session not found'})
    except Exception as e:
        db.session.rollback()
        emit('error', {'message': f'Failed to save notes: {str(e)}'})
        logger.error(f"Error saving notes: {str(e)}")

@socketio.on('end_session', namespace='/video-counseling')
def handle_end_session(data):
    """Handle session end"""
    session_id = data.get('session_id')
    if not session_id:
        return
    
    # Only counselor or student can end their own session
    session = CounselingSession.query.get(session_id)
    if not session:
        return
    
    has_permission = False
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and session.student_id == student.id:
            has_permission = True
    elif current_user.role in ['office_admin', 'super_admin']:
        if session.counselor_id == current_user.id or current_user.role == 'super_admin':
            has_permission = True
    
    if not has_permission:
        emit('error', {'message': 'Permission denied'})
        return
    
    room_name = f"video_session_{session_id}"
    
    # Update session status
    try:
        if session.status != 'completed':
            session.status = 'completed'
            session.ended_at = datetime.utcnow()
            
            # Save final notes if provided by counselor
            final_notes = data.get('final_notes', '')
            if final_notes and current_user.role in ['office_admin', 'super_admin']:
                if session.notes:
                    session.notes += f"\n\nFinal notes: {final_notes}"
                else:
                    session.notes = f"Final notes: {final_notes}"
            
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error ending session: {str(e)}")
    
    # Notify all participants
    emit('session_ended', {
        'session_id': session_id,
        'ended_by': current_user.get_full_name(),
        'ended_by_role': current_user.role,
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'ended_at': session.ended_at.isoformat() if session.ended_at else None,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name)
    
    # Clean up session data
    cleanup_session(session_id)
    
    logger.info(f"Session {session_id} ended by {current_user.id}")

@socketio.on('leave_session', namespace='/video-counseling')
def handle_leave_session(data):
    """Handle user leaving session"""
    session_id = data.get('session_id')
    if not session_id:
        return
    
    room_name = f"video_session_{session_id}"
    leave_room(room_name)
    
    # Remove user from active sessions
    if session_id in active_sessions and current_user.id in active_sessions[session_id]:
        del active_sessions[session_id][current_user.id]
    
    # Notify others
    emit('user_left', {
        'user_id': current_user.id,
        'name': current_user.get_full_name(),
        'role': current_user.role,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name)
    
    logger.info(f"User {current_user.id} left session {session_id}")

@socketio.on('connection_quality', namespace='/video-counseling')
def handle_connection_quality(data):
    """Handle connection quality updates"""
    session_id = data.get('session_id')
    quality_data = data.get('quality')
    
    if not session_id or not quality_data:
        return
    
    room_name = f"video_session_{session_id}"
    
    # Forward quality data to other participants
    emit('quality_update', {
        'user_id': current_user.id,
        'quality': quality_data,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)

@socketio.on('reconnect_request', namespace='/video-counseling')
def handle_reconnect_request(data):
    """Forward a reconnect request to peers to trigger renegotiation."""
    session_id = data.get('session_id')
    if not session_id:
        return
    room_name = f"video_session_{session_id}"
    emit('reconnect_request', {
        'user_id': current_user.id,
        'name': current_user.get_full_name(),
        'role': current_user.role,
        'session_id': session_id,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)

@socketio.on('screen_share_start', namespace='/video-counseling')
def handle_screen_share_start(data):
    """Handle screen sharing start (counselor only)"""
    if current_user.role not in ['office_admin', 'super_admin']:
        emit('error', {'message': 'Only counselors can share screen'})
        return
    
    session_id = data.get('session_id')
    if not session_id:
        return
    
    room_name = f"video_session_{session_id}"
    
    emit('screen_share_started', {
        'user_id': current_user.id,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)

@socketio.on('screen_share_stop', namespace='/video-counseling')
def handle_screen_share_stop(data):
    """Handle screen sharing stop"""
    session_id = data.get('session_id')
    if not session_id:
        return
    
    room_name = f"video_session_{session_id}"
    
    emit('screen_share_stopped', {
        'user_id': current_user.id,
        'name': current_user.get_full_name(),
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name, include_self=False)

@socketio.on('device_change', namespace='/video-counseling')
def handle_device_change(data):
    """Handle device change notification"""
    session_id = data.get('session_id')
    device_type = data.get('device_type')  # 'camera' or 'microphone'
    device_id = data.get('device_id')
    
    if not all([session_id, device_type]):
        return
    
    room_name = f"video_session_{session_id}"
    
    emit('user_device_changed', {
        'user_id': current_user.id,
        'device_type': device_type,
        'device_id': device_id,
        'name': current_user.get_full_name()
    }, room=room_name, include_self=False)

@socketio.on('session_heartbeat', namespace='/video-counseling')
def handle_session_heartbeat(data):
    """Handle session heartbeat to maintain connection"""
    session_id = data.get('session_id')
    if not session_id or session_id not in active_sessions:
        return
    
    if current_user.id in active_sessions[session_id]:
        active_sessions[session_id][current_user.id]['last_heartbeat'] = datetime.utcnow()
        
        # Store user session mapping
        user_sessions[current_user.id] = session_id
    
    emit('heartbeat_ack', {
        'timestamp': datetime.utcnow().isoformat()
    })

@socketio.on('request_session_info', namespace='/video-counseling')
def handle_request_session_info(data):
    """Handle request for current session information"""
    session_id = data.get('session_id')
    if not session_id:
        return
    
    session = CounselingSession.query.get(session_id)
    if not session:
        emit('error', {'message': 'Session not found'})
        return
    
    # Check user access
    has_access = False
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student and session.student_id == student.id:
            has_access = True
    elif current_user.role in ['office_admin', 'super_admin']:
        if session.counselor_id == current_user.id or current_user.role == 'super_admin':
            has_access = True
    
    if not has_access:
        emit('error', {'message': 'Access denied'})
        return
    
    # Get session info
    session_info = {
        'session_id': session.id,
        'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
        'status': session.status,
        'is_video_session': session.is_video_session,
        'student_name': session.student.user.get_full_name() if session.student else 'Unknown',
        'counselor_name': session.counselor.get_full_name() if session.counselor else 'Unknown',
        'office_name': session.office.name if session.office else 'Unknown',
        'notes': session.notes if current_user.role in ['office_admin', 'super_admin'] else None,
        'started_at': session.started_at.isoformat() if getattr(session, 'started_at', None) else None,
        'ended_at': session.ended_at.isoformat() if getattr(session, 'ended_at', None) else None
    }
    
    emit('session_info', session_info)

def check_session_ready(session_id, room_name):
    """Check if session is ready to start (both participants present and ready)"""
    if session_id not in active_sessions:
        return
    
    participants = active_sessions[session_id]
    
    # Check if we have both student and counselor
    has_student = any(p['role'] == 'student' for p in participants.values())
    has_counselor = any(p['role'] in ['office_admin', 'super_admin'] for p in participants.values())
    
    # Check if both are ready
    all_ready = all(p['ready'] for p in participants.values())
    
    # Only emit session_ready when we have the minimum requirements
    if has_student and has_counselor and len(participants) >= 2:
        status = 'ready' if all_ready else 'waiting_for_ready'
        
        emit('session_ready', {
            'session_id': session_id,
            'status': status,
            'all_ready': all_ready,
            'participants': [
                {
                    'user_id': p['user_id'],
                    'role': p['role'],
                    'name': p['name'],
                    'ready': p['ready']
                }
                for p in participants.values()
            ],
            'timestamp': datetime.utcnow().isoformat()
        }, room=room_name)
        
        if all_ready:
            logger.info(f"Session {session_id} is ready to start - all participants ready")
        else:
            logger.info(f"Session {session_id} has all participants but waiting for ready status")
    else:
        # Emit waiting status
        emit('session_waiting', {
            'session_id': session_id,
            'has_student': has_student,
            'has_counselor': has_counselor,
            'participant_count': len(participants),
            'participants': [
                {
                    'user_id': p['user_id'],
                    'role': p['role'],
                    'name': p['name'],
                    'ready': p['ready']
                }
                for p in participants.values()
            ],
            'timestamp': datetime.utcnow().isoformat()
        }, room=room_name)
        
        logger.info(f"Session {session_id} waiting - student: {has_student}, counselor: {has_counselor}, count: {len(participants)}")

def cleanup_user_sessions(user_id):
    """Clean up sessions when user disconnects"""
    sessions_to_clean = []
    for session_id, participants in active_sessions.items():
        if user_id in participants:
            sessions_to_clean.append(session_id)

    for session_id in sessions_to_clean:
        if user_id in active_sessions[session_id]:
            del active_sessions[session_id][user_id]

        # If session is empty, clean it up
        if not active_sessions[session_id]:
            del active_sessions[session_id]

def cleanup_session(session_id):
    """Clean up session data"""
    if session_id in active_sessions:
        del active_sessions[session_id]
    if session_id in session_rooms:
        del session_rooms[session_id]
