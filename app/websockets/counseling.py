from flask_socketio import emit, join_room, leave_room, rooms
from flask import request
from app.extensions import socketio, db
from flask_login import current_user
from app.models import CounselingSession, SessionParticipation, User, Student
from datetime import datetime
import logging
import json

# Configure logging
logger = logging.getLogger(__name__)

# Dictionary to track connected users and their session rooms
connected_users = {}
session_rooms = {}

@socketio.on('connect', namespace='/video-counseling')
def handle_connect():
    """Handle client connection to the video counseling namespace"""
    if not current_user.is_authenticated:
        logger.warning("Unauthenticated connection attempt to video counseling")
        return False
    
    user_id = current_user.id
    logger.info(f"User {user_id} connected to video counseling namespace")
    
    # Add user to connected users
    connected_users[user_id] = request.sid
    
    # Emit connection success
    emit('connection_success', {
        'user_id': user_id,
        'username': current_user.get_full_name(),
        'role': current_user.role
    })
    
    return True

@socketio.on('disconnect', namespace='/video-counseling')
def handle_disconnect():
    """Handle client disconnection from video counseling namespace"""
    if not current_user.is_authenticated:
        return
    
    user_id = current_user.id
    logger.info(f"User {user_id} disconnected from video counseling namespace")
    
    # Remove user from connected users
    if user_id in connected_users:
        del connected_users[user_id]
    
    # Find and notify sessions this user was in
    for session_id, participants in session_rooms.items():
        if user_id in participants:
            # Remove user from session room
            participants.remove(user_id)
            
            # Notify other participants
            for participant_id in participants:
                if participant_id in connected_users:
                    emit('user_disconnected', {
                        'user_id': user_id,
                        'username': current_user.get_full_name(),
                        'role': current_user.role
                    }, room=connected_users[participant_id])
            
            # Update session status in database if needed
            try:
                session = CounselingSession.query.get(int(session_id))
                if session:
                    # Update participation record
                    participation = SessionParticipation.query.filter_by(
                        session_id=session.id,
                        user_id=user_id,
                        left_at=None
                    ).order_by(SessionParticipation.joined_at.desc()).first()
                    
                    if participation:
                        participation.left_at = datetime.utcnow()
                        db.session.commit()
                        logger.info(f"Updated participation record for user {user_id} in session {session_id}")
            except Exception as e:
                logger.error(f"Error updating session on disconnect: {str(e)}")

@socketio.on('join_session', namespace='/video-counseling')
def handle_join_session(data):
    """Handle user joining a video counseling session"""
    if not current_user.is_authenticated:
        return
    
    user_id = current_user.id
    session_id = data.get('session_id')
    
    if not session_id:
        logger.error(f"User {user_id} attempted to join session without session_id")
        emit('error', {'message': 'Session ID is required'})
        return
    
    logger.info(f"User {user_id} joining session {session_id}")
    
    try:
        # Get session from database
        session = CounselingSession.query.get(int(session_id))
        if not session:
            logger.error(f"Session {session_id} not found")
            emit('error', {'message': 'Session not found'})
            return
        
        # Verify user has permission to join this session
        has_permission = False
        user_role = None
        
        if current_user.role == 'student':
            student = Student.query.filter_by(user_id=user_id).first()
            if student and session.student_id == student.id:
                has_permission = True
                user_role = 'student'
                # Update student waiting room status
                session.student_in_waiting_room = True
        elif current_user.role == 'office_admin':
            if session.counselor_id == user_id or session.office_id == current_user.office_admin.office_id:
                has_permission = True
                user_role = 'counselor'
                # Update counselor waiting room status
                session.counselor_in_waiting_room = True
                # Assign as counselor if not already assigned
                if not session.counselor_id:
                    session.counselor_id = user_id
        
        if not has_permission:
            logger.warning(f"User {user_id} denied access to session {session_id}")
            emit('error', {'message': 'You do not have permission to join this session'})
            return
        
        # Join the session room
        room_name = f"session_{session_id}"
        join_room(room_name)
        
        # Track user in session_rooms
        if session_id not in session_rooms:
            session_rooms[session_id] = []
        if user_id not in session_rooms[session_id]:
            session_rooms[session_id].append(user_id)
        
        # Get other participant info
        other_participant = None
        if user_role == 'student' and session.counselor_id:
            counselor = User.query.get(session.counselor_id)
            if counselor:
                other_participant = {
                    'user_id': counselor.id,
                    'username': counselor.get_full_name(),
                    'role': 'counselor'
                }
        elif user_role == 'counselor':
            student = Student.query.get(session.student_id)
            if student and student.user:
                other_participant = {
                    'user_id': student.user.id,
                    'username': student.user.get_full_name(),
                    'role': 'student'
                }
        
        # Check if both participants are in the waiting room
        both_waiting = session.student_in_waiting_room and session.counselor_in_waiting_room
        
        # If both participants are waiting, set call_started_at
        if both_waiting and not session.call_started_at:
            session.call_started_at = datetime.utcnow()
        
        # Save changes to database
        db.session.commit()
        
        # Notify user of successful join
        emit('session_joined', {
            'session_id': session_id,
            'user_role': user_role,
            'waiting_room_status': session.get_waiting_room_status(),
            'other_participant': other_participant,
            'call_started': session.call_started_at is not None
        })
        
        # Notify other participants in the room
        emit('user_joined', {
            'user_id': user_id,
            'username': current_user.get_full_name(),
            'role': user_role,
            'waiting_room_status': session.get_waiting_room_status(),
            'call_started': session.call_started_at is not None
        }, room=room_name, include_self=False)
        
        # If both participants are now in the room, notify them to start the call
        if both_waiting:
            emit('start_call', {
                'session_id': session_id,
                'timestamp': session.call_started_at.isoformat() if session.call_started_at else datetime.utcnow().isoformat()
            }, room=room_name)
            
            logger.info(f"Both participants in session {session_id}, starting call")
    
    except Exception as e:
        logger.error(f"Error in join_session: {str(e)}")
        emit('error', {'message': f'An error occurred: {str(e)}'})

@socketio.on('leave_session', namespace='/video-counseling')
def handle_leave_session(data):
    """Handle user leaving a video counseling session"""
    if not current_user.is_authenticated:
        return
    
    user_id = current_user.id
    session_id = data.get('session_id')
    
    if not session_id:
        logger.error(f"User {user_id} attempted to leave session without session_id")
        return
    
    logger.info(f"User {user_id} leaving session {session_id}")
    
    try:
        # Leave the session room
        room_name = f"session_{session_id}"
        leave_room(room_name)
        
        # Remove user from session_rooms
        if session_id in session_rooms and user_id in session_rooms[session_id]:
            session_rooms[session_id].remove(user_id)
        
        # Get session from database
        session = CounselingSession.query.get(int(session_id))
        if session:
            # Update waiting room status
            if current_user.role == 'student':
                session.student_in_waiting_room = False
            elif current_user.role == 'office_admin':
                session.counselor_in_waiting_room = False
            
            # Update participation record
            participation = SessionParticipation.query.filter_by(
                session_id=session.id,
                user_id=user_id,
                left_at=None
            ).order_by(SessionParticipation.joined_at.desc()).first()
            
            if participation:
                participation.left_at = datetime.utcnow()
            
            db.session.commit()
        
        # Notify other participants
        emit('user_left', {
            'user_id': user_id,
            'username': current_user.get_full_name(),
            'role': current_user.role
        }, room=room_name)
        
    except Exception as e:
        logger.error(f"Error in leave_session: {str(e)}")

# WebRTC Signaling
@socketio.on('offer', namespace='/video-counseling')
def handle_offer(data):
    """Handle WebRTC offer from client"""
    if not current_user.is_authenticated:
        return
    
    target_id = data.get('target')
    session_id = data.get('session_id')
    offer = data.get('offer')
    
    logger.info(f"Received offer from {current_user.id} to {target_id} for session {session_id}")
    
    if target_id in connected_users:
        emit('offer', {
            'offer': offer,
            'sender': current_user.id,
            'sender_name': current_user.get_full_name(),
            'sender_role': current_user.role,
            'session_id': session_id
        }, room=connected_users[target_id])
    else:
        logger.warning(f"Target user {target_id} not connected, cannot forward offer")

@socketio.on('answer', namespace='/video-counseling')
def handle_answer(data):
    """Handle WebRTC answer from client"""
    if not current_user.is_authenticated:
        return
    
    target_id = data.get('target')
    session_id = data.get('session_id')
    answer = data.get('answer')
    
    logger.info(f"Received answer from {current_user.id} to {target_id} for session {session_id}")
    
    if target_id in connected_users:
        emit('answer', {
            'answer': answer,
            'sender': current_user.id,
            'session_id': session_id
        }, room=connected_users[target_id])
    else:
        logger.warning(f"Target user {target_id} not connected, cannot forward answer")

@socketio.on('ice_candidate', namespace='/video-counseling')
def handle_ice_candidate(data):
    """Handle ICE candidate from client"""
    if not current_user.is_authenticated:
        return
    
    target_id = data.get('target')
    session_id = data.get('session_id')
    candidate = data.get('candidate')
    
    logger.debug(f"Received ICE candidate from {current_user.id} to {target_id}")
    
    if target_id in connected_users:
        emit('ice_candidate', {
            'candidate': candidate,
            'sender': current_user.id,
            'session_id': session_id
        }, room=connected_users[target_id])
    else:
        logger.warning(f"Target user {target_id} not connected, cannot forward ICE candidate")

@socketio.on('toggle_audio', namespace='/video-counseling')
def handle_toggle_audio(data):
    """Handle audio toggle event"""
    if not current_user.is_authenticated:
        return
    
    session_id = data.get('session_id')
    audio_enabled = data.get('enabled')
    
    logger.info(f"User {current_user.id} toggled audio: {audio_enabled} in session {session_id}")
    
    # Broadcast to all users in the session room
    room_name = f"session_{session_id}"
    emit('audio_state_changed', {
        'user_id': current_user.id,
        'enabled': audio_enabled
    }, room=room_name, include_self=False)

@socketio.on('toggle_video', namespace='/video-counseling')
def handle_toggle_video(data):
    """Handle video toggle event"""
    if not current_user.is_authenticated:
        return
    
    session_id = data.get('session_id')
    video_enabled = data.get('enabled')
    
    logger.info(f"User {current_user.id} toggled video: {video_enabled} in session {session_id}")
    
    # Broadcast to all users in the session room
    room_name = f"session_{session_id}"
    emit('video_state_changed', {
        'user_id': current_user.id,
        'enabled': video_enabled
    }, room=room_name, include_self=False)

@socketio.on('chat_message', namespace='/video-counseling')
def handle_chat_message(data):
    """Handle in-call chat message"""
    if not current_user.is_authenticated:
        return
    
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not message or not message.strip():
        return
    
    logger.info(f"User {current_user.id} sent chat message in session {session_id}")
    
    # Broadcast to all users in the session room
    room_name = f"session_{session_id}"
    emit('chat_message', {
        'user_id': current_user.id,
        'username': current_user.get_full_name(),
        'role': current_user.role,
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    }, room=room_name)

@socketio.on('end_session', namespace='/video-counseling')
def handle_end_session(data):
    """Handle ending a counseling session"""
    if not current_user.is_authenticated:
        return
    
    session_id = data.get('session_id')
    notes = data.get('notes', '')
    
    logger.info(f"User {current_user.id} ending session {session_id}")
    
    try:
        # Get session from database
        session = CounselingSession.query.get(int(session_id))
        if not session:
            emit('error', {'message': 'Session not found'})
            return
        
        # Verify user has permission to end this session
        has_permission = False
        
        if current_user.role == 'office_admin' and session.counselor_id == current_user.id:
            has_permission = True
        
        if not has_permission:
            emit('error', {'message': 'You do not have permission to end this session'})
            return
        
        # Update session status
        session.status = 'completed'
        session.session_ended_at = datetime.utcnow()
        
        # Update notes if provided
        if notes:
            session.notes = notes
        
        # Save changes to database
        db.session.commit()
        
        # Notify all participants
        room_name = f"session_{session_id}"
        emit('session_ended', {
            'session_id': session_id,
            'ended_by': {
                'user_id': current_user.id,
                'username': current_user.get_full_name(),
                'role': current_user.role
            },
            'timestamp': session.session_ended_at.isoformat()
        }, room=room_name)
        
        logger.info(f"Session {session_id} ended successfully")
    
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        emit('error', {'message': f'An error occurred: {str(e)}'})
