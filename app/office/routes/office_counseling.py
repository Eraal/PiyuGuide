from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, SessionParticipation, 
    SessionRecording, SessionReminder, Notification
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from app.office import office_bp
from app.office.routes.office_dashboard import get_office_context
import uuid
import os
from flask_apscheduler import APScheduler

# Create the scheduler but don't initialize it yet
scheduler = APScheduler()

# Store a reference to the Flask app
flask_app = None

# Function to initialize the scheduler with the Flask app
def init_scheduler(app):
    global flask_app
    flask_app = app
    scheduler.init_app(app)
    scheduler.start()

# Define the scheduled task
@scheduler.task('interval', id='check_upcoming_sessions', seconds=60)
def check_upcoming_sessions():
    """
    Check for upcoming sessions and automatically change status to in_progress
    and send notifications to students with video links when appropriate
    """
    global flask_app
    
    if not flask_app:
        print("Error: Flask app not initialized for scheduler")
        return
    
    # Use the application context from the stored Flask app
    with flask_app.app_context():
        now = datetime.utcnow()
        
        # Find sessions that are scheduled to start within the next 15 minutes but not yet started
        upcoming_sessions = CounselingSession.query.filter(
            CounselingSession.status.in_(['confirmed', 'pending']),
            CounselingSession.is_video_session == True,
            CounselingSession.scheduled_at <= now + timedelta(minutes=15),
            CounselingSession.scheduled_at >= now
        ).all()
        
        for session in upcoming_sessions:
            # Generate meeting details if they don't exist
            if not session.meeting_id:
                session.generate_meeting_details()
            
            # Set status to in_progress if within 5 minutes of start time
            if session.scheduled_at <= now + timedelta(minutes=5):
                session.status = 'in_progress'
                
                # Send notification to student with the video link
                student = Student.query.get(session.student_id)
                if student:
                    notification = Notification(
                        user_id=student.user_id,
                        title="Your Video Session is Ready",
                        message=f"Your counseling session is starting soon. Click here to join the video call.",
                        source_office_id=session.office_id,
                        is_read=False,
                        link=f"/student/view-session/{session.id}",
                        notification_type="video_session"
                    )
                    db.session.add(notification)
            
            # Send reminder notification at 15 minutes before session
            elif session.scheduled_at <= now + timedelta(minutes=15):
                student = Student.query.get(session.student_id)
                if student:
                    # Check if a reminder was already sent in the last hour
                    recent_reminder = Notification.query.filter(
                        Notification.user_id == student.user_id,
                        Notification.title.like("%Video Session Reminder%"),
                        Notification.created_at >= now - timedelta(hours=1),
                        Notification.source_office_id == session.office_id
                    ).first()
                    
                    if not recent_reminder:
                        notification = Notification(
                            user_id=student.user_id,
                            title="Video Session Reminder",
                            message=f"Your counseling session is scheduled to begin in {int((session.scheduled_at - now).total_seconds() / 60)} minutes.",
                            source_office_id=session.office_id,
                            is_read=False,
                            link=f"/student/view-session/{session.id}",
                            notification_type="reminder"
                        )
                        db.session.add(notification)
        
        db.session.commit()


@office_bp.route('/video-counseling')
@login_required
def video_counseling():
    """View all video counseling sessions for the office"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    
    # Get filter parameters
    status = request.args.get('status', 'upcoming')
    date_range = request.args.get('date_range', '7d')
    page = request.args.get('page', 1, type=int)
    
    # Only get video sessions
    query = CounselingSession.query.filter_by(
        office_id=office_id,
        is_video_session=True
    )
    
    # Apply status filter
    now = datetime.utcnow()
    if status == 'upcoming':
        query = query.filter(
            CounselingSession.status.in_(['pending', 'confirmed']),
            CounselingSession.scheduled_at > now
        )
    elif status == 'today':
        today_start = datetime.combine(now.date(), datetime.min.time())
        today_end = datetime.combine(now.date(), datetime.max.time())
        query = query.filter(
            CounselingSession.scheduled_at >= today_start,
            CounselingSession.scheduled_at <= today_end
        )
    elif status == 'active':
        query = query.filter(
            CounselingSession.status == 'in_progress'
        )
    elif status == 'past':
        query = query.filter(
            CounselingSession.status == 'completed'
        )
    elif status != 'all':
        query = query.filter_by(status=status)
    
    # Apply date range filter
    if date_range == '7d' and status == 'upcoming':
        query = query.filter(CounselingSession.scheduled_at <= now + timedelta(days=7))
    elif date_range == '30d' and status == 'upcoming':
        query = query.filter(CounselingSession.scheduled_at <= now + timedelta(days=30))
    elif date_range == '7d' and status == 'past':
        query = query.filter(CounselingSession.scheduled_at >= now - timedelta(days=7))
    elif date_range == '30d' and status == 'past':
        query = query.filter(CounselingSession.scheduled_at >= now - timedelta(days=30))
    
    # Filter by counselor (only show sessions assigned to the current user)
    if request.args.get('my_sessions', 'false') == 'true':
        query = query.filter_by(counselor_id=current_user.id)
    
    # Sort by scheduled date
    if status == 'upcoming' or status == 'today':
        query = query.order_by(CounselingSession.scheduled_at)
    else:
        query = query.order_by(desc(CounselingSession.scheduled_at))
    
    # Make sure all sessions have meeting links generated
    for session in query:
        if session.status in ['pending', 'confirmed', 'in_progress'] and not session.meeting_id:
            session.generate_meeting_details()
    
    db.session.commit()
    
    # Paginate results
    video_sessions = query.paginate(page=page, per_page=10, error_out=False)
    
    # Get stats for sidebar
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    
    today_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session == True,
        CounselingSession.scheduled_at >= today_start,
        CounselingSession.scheduled_at <= today_end
    ).count()
    
    active_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session == True,
        CounselingSession.status == 'in_progress'
    ).count()
    
    upcoming_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session == True,
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).count()
    
    completed_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session == True,
        CounselingSession.status == 'completed'
    ).count()
    
    my_upcoming_sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session == True,
        CounselingSession.counselor_id == current_user.id,
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).order_by(CounselingSession.scheduled_at).limit(5).all()
    
    # Calculate count of pending inquiries for the notification badge
    pending_inquiries_count = Inquiry.query.filter_by(
        office_id=office_id, 
        status='pending'
    ).count()
    
    context = get_office_context()
    context.update({
        'video_sessions': video_sessions,
        'status': status,
        'date_range': date_range,
        'today_video_count': today_video_count,
        'active_video_count': active_video_count,
        'upcoming_video_count': upcoming_video_count,
        'completed_video_count': completed_video_count,
        'my_upcoming_sessions': my_upcoming_sessions,
        'pending_inquiries_count': pending_inquiries_count,
        'now': now
    })
    
    return render_template('office/office_counseling.html', **context)


@office_bp.route('/video-session/<int:session_id>')
@login_required
def join_video_session(session_id):
    """Join a specific video counseling session"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    session = CounselingSession.query.filter_by(
        id=session_id, 
        office_id=office_id,
        is_video_session=True
    ).first_or_404()
    
    # Check if counselor is assigned to this session
    if session.counselor_id != current_user.id:
        # Instead of preventing access, assign the current admin as the counselor
        session.counselor_id = current_user.id
        flash('You have been assigned as the counselor for this session.', 'success')
    
    # Check if session is already completed
    if session.status == 'completed':
        flash('This session has already been completed. You can still view the details.', 'info')
        # Continue to allow viewing the session details instead of redirecting
    
    # Check if session is cancelled
    if session.status == 'cancelled':
        flash('This session has been cancelled. You can still view the details.', 'warning')
        # Continue to allow viewing the session details instead of redirecting
    
    # Get student information
    student = Student.query.get(session.student_id)
    student_user = User.query.get(student.user_id)
    
    # If session doesn't have meeting details, generate them
    if not session.meeting_id:
        session.generate_meeting_details()
        db.session.commit()
    
    # Update the session status to in_progress if it's not completed or cancelled
    now = datetime.utcnow()
    scheduled_time = session.scheduled_at
    
    # Changed time window restriction - always allow joining if not completed/cancelled
    if session.status not in ['completed', 'cancelled']:
        session.status = 'in_progress'
        
        # Send notification to student with link if not already sent
        student = Student.query.get(session.student_id)
        if student:
            # Check if a notification was already sent in the last hour
            recent_notification = Notification.query.filter(
                Notification.user_id == student.user_id,
                Notification.title == "Your Video Session is Ready",
                Notification.created_at >= now - timedelta(hours=1),
                Notification.source_office_id == session.office_id
            ).first()
            
            if not recent_notification:
                notification = Notification(
                    user_id=student.user_id,
                    title="Your Video Session is Ready",
                    message=f"Your counseling session is starting. Click here to join the video call.",
                    source_office_id=session.office_id,
                    is_read=False,
                    link=f"/student/view-session/{session.id}",
                    notification_type="video_session"
                )
                db.session.add(notification)
        
        db.session.commit()
    
    # Log counselor joining the session
    session.counselor_joined_at = now
    
    # Create participation record
    participation = SessionParticipation(
        session_id=session_id,
        user_id=current_user.id,
        joined_at=now,
        device_info=request.user_agent.string,
        ip_address=request.remote_addr
    )
    db.session.add(participation)
    
    # Log activity
    AuditLog.log_action(
        actor=current_user,
        action="Joined video counseling session",
        target_type="counseling_session",
        status=session.status,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    db.session.commit()
    
    # Calculate count of pending inquiries for the notification badge
    pending_inquiries_count = Inquiry.query.filter_by(
        office_id=office_id, 
        status='pending'
    ).count()
    
    context = get_office_context()
    context.update({
        'session': session,
        'student': student,
        'student_user': student_user,
        'meeting_url': session.meeting_url,
        'meeting_id': session.meeting_id,
        'meeting_password': session.meeting_password,
        'pending_inquiries_count': pending_inquiries_count
    })
    
    return render_template('office/video_session.html', **context)


@office_bp.route('/video-session/<int:session_id>/end', methods=['POST'])
@login_required
def end_video_session(session_id):
    """End a video counseling session"""
    if current_user.role != 'office_admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    session = CounselingSession.query.filter_by(
        id=session_id,
        is_video_session=True
    ).first_or_404()
    
    # Check if counselor is assigned to this session
    if session.counselor_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'You are not assigned as the counselor for this session'}), 403
    
    # Update session status
    session.status = 'completed'
    session.session_ended_at = datetime.utcnow()
    
    # Update participation record
    participation = SessionParticipation.query.filter_by(
        session_id=session_id,
        user_id=current_user.id,
        left_at=None
    ).order_by(desc(SessionParticipation.joined_at)).first()
    
    if participation:
        participation.left_at = datetime.utcnow()
    
    # Get notes from the request
    notes = request.form.get('notes', '')
    if notes:
        session.notes = notes
    
    # Handle recording if it exists
    recording_data = request.form.get('recording_data')
    if recording_data:
        # Create directory if it doesn't exist
        recordings_dir = os.path.join('static', 'uploads', 'recordings')
        if not os.path.exists(recordings_dir):
            os.makedirs(recordings_dir)
        
        # Save recording file
        recording_filename = f"session_{session_id}_{uuid.uuid4().hex}.webm"
        recording_path = os.path.join(recordings_dir, recording_filename)
        
        # Save recording to file
        with open(recording_path, 'wb') as f:
            f.write(recording_data)
        
        # Create recording record
        recording = SessionRecording(
            session_id=session_id,
            recording_path=recording_path,
            counselor_consent=True,  # Counselor recorded it
            student_consent=request.form.get('student_consent', 'false') == 'true'
        )
        db.session.add(recording)
    
    # Log activity
    AuditLog.log_action(
        actor=current_user,
        action="Ended video counseling session",
        target_type="counseling_session",
        status='completed',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Session ended successfully'})


@office_bp.route('/video-session/<int:session_id>/update-status', methods=['POST'])
@login_required
def update_session_status(session_id):
    """Update status of a counseling session"""
    if current_user.role != 'office_admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    session = CounselingSession.query.filter_by(id=session_id).first_or_404()
    
    # Check if office admin belongs to the office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'status': 'error', 'message': 'You do not have permission to update this session'}), 403
    
    new_status = request.form.get('status')
    if new_status not in ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no-show']:
        return jsonify({'status': 'error', 'message': 'Invalid status'}), 400
    
    # Update session status
    old_status = session.status
    session.status = new_status
    
    # If confirming the session, assign the current office admin as the counselor
    # and generate meeting details for video sessions
    if new_status == 'confirmed' and (session.counselor_id is None or session.counselor_id != current_user.id):
        session.counselor_id = current_user.id
        
        # Generate meeting details for video sessions immediately upon confirmation
        if session.is_video_session and not session.meeting_id:
            session.generate_meeting_details()
        
        # Create a notification for the student
        from app.models import Notification, Student
        student = Student.query.get(session.student_id)
        if student:
            notification = Notification(
                user_id=student.user_id,
                title="Counseling Session Confirmed",
                message=f"Your counseling session scheduled for {session.scheduled_at.strftime('%Y-%m-%d %H:%M')} has been confirmed.",
                source_office_id=session.office_id,
                is_read=False,
                link=f"/student/view-session/{session.id}" if session.is_video_session else None,
                notification_type="video_session" if session.is_video_session else "confirmation"
            )
            db.session.add(notification)
    
    # If cancelling, record cancellation reason
    if new_status == 'cancelled':
        reason = request.form.get('reason', '')
        if session.notes:
            session.notes += f"\n\nCancellation reason: {reason}"
        else:
            session.notes = f"Cancellation reason: {reason}"
        
        # Create a notification for the student
        from app.models import Notification, Student
        student = Student.query.get(session.student_id)
        if student:
            notification = Notification(
                user_id=student.user_id,
                title="Counseling Session Cancelled",
                message=f"Your counseling session scheduled for {session.scheduled_at.strftime('%Y-%m-%d %H:%M')} has been cancelled.",
                source_office_id=session.office_id,
                is_read=False
            )
            db.session.add(notification)
    
    # Log activity
    AuditLog.log_action(
        actor=current_user,
        action=f"Updated video session status from '{old_status}' to '{new_status}'",
        target_type="counseling_session",
        status=new_status,
        is_success=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'Session status updated to {new_status}'})


@office_bp.route('/video-session/<int:session_id>/send-reminder', methods=['POST'])
@login_required
def send_session_reminder(session_id):
    """Send a reminder for a counseling session"""
    if current_user.role != 'office_admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    session = CounselingSession.query.filter_by(id=session_id).first_or_404()
    
    # Check if office admin belongs to the office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'status': 'error', 'message': 'You do not have permission for this session'}), 403
    
    reminder_type = request.form.get('type', 'in_app')
    
    # Get the student
    student = Student.query.get(session.student_id)
    student_user = User.query.get(student.user_id)
    
    reminder = SessionReminder(
        session_id=session_id,
        user_id=student_user.id,
        reminder_type=reminder_type,
        scheduled_at=datetime.utcnow(),
        sent_at=datetime.utcnow(),
        status='sent'
    )
    db.session.add(reminder)
    
    # For in-app notifications, create a notification
    if reminder_type == 'in_app':
        from app.models import Notification
        
        notification = Notification(
            user_id=student_user.id,
            title="Counseling Reminder",
            message=f"Reminder: You have a video counseling session scheduled for {session.scheduled_at.strftime('%Y-%m-%d %H:%M')}. Please be ready to join the session on time."
        )
        db.session.add(notification)
    
    # Log activity
    AuditLog.log_action(
        actor=current_user,
        action=f"Sent {reminder_type} session reminder",
        target_type="counseling_session",
        status=session.status,
        is_success=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    db.session.commit()
    
    return jsonify({
        'status': 'success', 
        'message': f'{reminder_type.capitalize()} reminder sent to student'
    })


@office_bp.route('/video-session/<int:session_id>/reschedule', methods=['POST'])
@login_required
def reschedule_session(session_id):
    """Reschedule a counseling session"""
    if current_user.role != 'office_admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    session = CounselingSession.query.filter_by(id=session_id).first_or_404()
    
    # Check if office admin belongs to the office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'status': 'error', 'message': 'You do not have permission to reschedule this session'}), 403
    
    # Only allow rescheduling if the session is pending or confirmed
    if session.status not in ['pending', 'confirmed']:
        return jsonify({'status': 'error', 'message': 'Only pending or confirmed sessions can be rescheduled'}), 400

    # Get new date and time from request (matching the parameter names used in JS)
    new_date = request.form.get('reschedule_date')
    new_time = request.form.get('reschedule_time')
    
    if not new_date or not new_time:
        return jsonify({'status': 'error', 'message': 'Date and time are required'}), 400
    
    try:
        # Parse the date and time
        new_datetime = datetime.strptime(f"{new_date} {new_time}", '%Y-%m-%d %H:%M')
        
        # Store original datetime for notification
        original_datetime = session.scheduled_at
        
        # Update session with new datetime
        session.scheduled_at = new_datetime
        
        # Set session status to confirmed since an office admin has reviewed it
        if session.status == 'pending':
            session.status = 'confirmed'
        
        # Add a note about rescheduling
        if session.notes:
            session.notes += f"\n\nRescheduled: Session was moved from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')} by {current_user.get_full_name()}."
        else:
            session.notes = f"Rescheduled: Session was moved from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')} by {current_user.get_full_name()}."
        
        # Create notification for student
        from app.models import Notification
        student = Student.query.get(session.student_id)
        notification = Notification(
            user_id=student.user_id,
            title="Counseling Session Rescheduled",
            message=f"Your counseling session has been rescheduled to {new_datetime.strftime('%Y-%m-%d %H:%M')}."
        )
        db.session.add(notification)
        
        # Log activity
        AuditLog.log_action(
            actor=current_user,
            action=f"Rescheduled counseling session from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')}",
            target_type="counseling_session",
            status=session.status,
            is_success=True,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({
            'status': 'success', 
            'message': 'Session rescheduled successfully',
            'new_time': new_datetime.strftime('%Y-%m-%d %H:%M')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Error rescheduling session: {str(e)}'}), 500


@office_bp.route('/video-session/<int:session_id>/save-notes', methods=['POST'])
@login_required
def save_session_notes(session_id):
    """Save notes for a video counseling session"""
    # Verify user is a counselor for this session
    session = CounselingSession.query.filter_by(
        id=session_id,
        counselor_id=current_user.id
    ).first_or_404()
    
    try:
        data = request.json
        notes = data.get('notes', '')
        
        # Update session notes
        session.notes = notes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notes saved successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error saving notes: {str(e)}'
        }), 500