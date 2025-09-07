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
from app.utils import role_required
import uuid
import os
from flask_apscheduler import APScheduler
from app.websockets.student import push_student_notification_to_user, push_student_session_update
from datetime import datetime, timedelta, time as dtime

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
                    # Flush to assign ID before emit
                    try:
                        db.session.flush()
                        from app.websockets.student import push_student_notification_to_user
                        payload = {
                            'id': notification.id,
                            'title': notification.title,
                            'message': notification.message,
                            'notification_type': notification.notification_type,
                            'source_office_id': notification.source_office_id,
                            'link': notification.link,
                            'timestamp': datetime.utcnow().isoformat(),
                        }
                        push_student_notification_to_user(student.user_id, payload)
                        # Realtime session status to student
                        try:
                            push_student_session_update(student.user_id, {
                                'session_id': session.id,
                                'status': 'in_progress',
                                'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                                'is_video_session': True,
                                'link': f"/student/view-session/{session.id}"
                            })
                        except Exception:
                            pass
                    except Exception:
                        pass
            
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
                        # Flush to assign ID before emit
                        try:
                            db.session.flush()
                            from app.websockets.student import push_student_notification_to_user
                            payload = {
                                'id': notification.id,
                                'title': notification.title,
                                'message': notification.message,
                                'notification_type': notification.notification_type,
                                'source_office_id': notification.source_office_id,
                                'link': notification.link,
                                'timestamp': datetime.utcnow().isoformat(),
                            }
                            push_student_notification_to_user(student.user_id, payload)
                        except Exception:
                            pass
        
        db.session.commit()


@office_bp.route('/video-counseling')
@login_required
def video_counseling():
    """View all video counseling sessions for the office"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    # If office doesn't offer counseling at all, redirect away
    try:
        from app.models import OfficeConcernType
        has_counseling_types = db.session.query(OfficeConcernType.id).filter(
            OfficeConcernType.office_id == office_id,
            OfficeConcernType.for_counseling.is_(True)
        ).first() is not None
        has_any_sessions = db.session.query(CounselingSession.id).filter(
            CounselingSession.office_id == office_id
        ).first() is not None
        if not (has_counseling_types or has_any_sessions):
            flash('Counseling is not enabled for your office.', 'warning')
            return redirect(url_for('office.dashboard'))
    except Exception:
        pass
    
    # Get filter parameters
    # Default to 'upcoming' so the initial view prioritizes upcoming (student-submitted) sessions
    status = request.args.get('status', 'upcoming')
    # Broaden default date range to 'all' so future sessions beyond 7 days are visible by default
    date_range = request.args.get('date_range', 'all')
    page = request.args.get('page', 1, type=int)
    
    # Base query now includes BOTH video and in-person sessions so that newly
    # submitted in-person requests appear in the dashboard immediately.
    # (User request: show in-person sessions that previously were hidden.)
    query = CounselingSession.query.filter_by(
        office_id=office_id
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
    
    # Paginate results first
    video_sessions = query.paginate(page=page, per_page=10, error_out=False)

    # Generate meeting details ONLY for the sessions in the current page that need them
    for session in video_sessions.items:
        if session.is_video_session and session.status in ['pending', 'confirmed', 'in_progress'] and not session.meeting_id:
            session.generate_meeting_details()
    db.session.commit()
    
    # Get stats for sidebar
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    
    # Preserve existing video-only stats for the cards
    today_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session.is_(True),
        CounselingSession.scheduled_at >= today_start,
        CounselingSession.scheduled_at <= today_end
    ).count()
    
    active_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session.is_(True),
        CounselingSession.status == 'in_progress'
    ).count()
    
    upcoming_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session.is_(True),
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).count()
    
    completed_video_count = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session.is_(True),
        CounselingSession.status == 'completed'
    ).count()
    
    my_upcoming_sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.is_video_session.is_(True),
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
        # Push realtime status to student
        try:
            push_student_session_update(student.user_id, {
                'session_id': session.id,
                'status': 'in_progress',
                'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                'is_video_session': True,
                'link': f"/student/view-session/{session.id}"
            })
        except Exception:
            pass
    
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
    session.ended_at = datetime.utcnow()
    
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
    
    # Check if this is an AJAX request or form submission
    if request.headers.get('Content-Type') == 'application/json' or request.is_json:
        return jsonify({
            'status': 'success', 
            'message': 'Session ended successfully',
            'redirect_url': url_for('office.session_completed', session_id=session_id)
        })
    else:
        # Direct form submission - redirect to session completion page
        flash('Session ended successfully!', 'success')
        return redirect(url_for('office.session_completed', session_id=session_id))


@office_bp.route('/video-session/<int:session_id>/complete', methods=['POST', 'GET'])
@login_required
def complete_session(session_id):
    """Complete a counseling session and redirect to completion page"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to complete this session.', 'error')
        return redirect(url_for('main.index'))
    
    session = CounselingSession.query.get_or_404(session_id)
    
    # Check if the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        flash('Access denied. You do not have permission to complete this session.', 'error')
        return redirect(url_for('office.video_counseling'))
    
    # Check if counselor is assigned to this session or allow any office admin to complete
    if session.counselor_id and session.counselor_id != current_user.id:
        flash('Access denied. You are not assigned as the counselor for this session.', 'error')
        return redirect(url_for('office.video_counseling'))
    
    # If no counselor assigned, assign current user
    if not session.counselor_id:
        session.counselor_id = current_user.id
    
    # Update session status and end time
    session.status = 'completed'
    session.ended_at = datetime.utcnow()
    
    # Get notes from form if provided
    if request.method == 'POST':
        notes = request.form.get('notes', '')
        if notes:
            if session.notes:
                session.notes += f"\n\nSession completion notes: {notes}"
            else:
                session.notes = notes
    
    # Log activity
    AuditLog.log_action(
        actor=current_user,
        action="Completed counseling session",
        target_type="counseling_session",
        target_id=session_id,
        status='completed',
        office=current_user.office_admin.office,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    try:
        db.session.commit()
        flash('Session completed successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing session: {str(e)}', 'error')
        return redirect(url_for('office.video_counseling'))
    
    # Redirect to session completion page
    return redirect(url_for('office.session_completed', session_id=session_id))


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
                # Use a type that maps to a green toast in the student UI
                notification_type="scheduled"
            )
            db.session.add(notification)
            # Flush to obtain ID, then push realtime event
            try:
                db.session.flush()
                payload = {
                    'id': getattr(notification, 'id', None),
                    'title': notification.title,
                    'message': notification.message,
                    'notification_type': notification.notification_type,
                    'source_office_id': notification.source_office_id,
                    'target_office_name': session.office.name if session.office else None,
                    'link': notification.link,
                    'created_at': datetime.utcnow().isoformat()
                }
                push_student_notification_to_user(student.user_id, payload)
                # Also emit realtime session update for student view page
                try:
                    push_student_session_update(student.user_id, {
                        'session_id': session.id,
                        'status': 'confirmed',
                        'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                        'is_video_session': bool(session.is_video_session),
                        'link': f"/student/view-session/{session.id}" if session.is_video_session else None
                    })
                except Exception:
                    pass
            except Exception:
                # Non-fatal if emit fails
                pass
    
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
                is_read=False,
                link=f"/student/counseling-sessions",
                # Map to red toast via 'error'
                notification_type="cancelled_error"
            )
            db.session.add(notification)
            try:
                db.session.flush()
                payload = {
                    'id': getattr(notification, 'id', None),
                    'title': notification.title,
                    'message': notification.message,
                    'notification_type': notification.notification_type,
                    'source_office_id': notification.source_office_id,
                    'target_office_name': session.office.name if session.office else None,
                    'link': notification.link,
                    'created_at': datetime.utcnow().isoformat()
                }
                push_student_notification_to_user(student.user_id, payload)
                try:
                    push_student_session_update(student.user_id, {
                        'session_id': session.id,
                        'status': 'cancelled',
                        'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                        'is_video_session': bool(session.is_video_session),
                        'link': f"/student/counseling-sessions"
                    })
                except Exception:
                    pass
            except Exception:
                pass
    
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
    # Emit realtime session update regardless of branch
    try:
        student = Student.query.get(session.student_id)
        if student:
            push_student_session_update(student.user_id, {
                'session_id': session.id,
                'status': new_status,
                'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                'is_video_session': bool(session.is_video_session),
                'link': f"/student/view-session/{session.id}" if session.is_video_session else None
            })
    except Exception:
        pass

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
    
    # For in-app notifications, create a notification and broadcast to the student in real-time
    if reminder_type == 'in_app':
        from app.models import Notification
        from app.websockets.student import push_student_notification_to_user

        # Build a richer notification including linkage and typing for client UI
        notification = Notification(
            user_id=student_user.id,
            title="Counseling Reminder",
            message=f"Reminder: You have a video counseling session scheduled for {session.scheduled_at.strftime('%Y-%m-%d %H:%M')}. Please be ready to join the session on time.",
            source_office_id=session.office_id,
            link=f"/student/view-session/{session.id}",
            notification_type="reminder",
            is_read=False,
            created_at=datetime.utcnow(),
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

    # Emit real-time event to student if in-app reminder
    if reminder_type == 'in_app':
        try:
            payload = {
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'notification_type': notification.notification_type,
                'source_office_id': notification.source_office_id,
                'link': notification.link,
                'timestamp': notification.created_at.isoformat(),
            }
            push_student_notification_to_user(student_user.id, payload)
        except Exception:
            # Non-fatal if websocket layer is unavailable
            pass
    
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
        # Prevent double-booking within the office: block if overlapping with another active session
        new_end = new_datetime + timedelta(minutes=session.duration_minutes or 60)
        candidates = CounselingSession.query.filter(
            CounselingSession.office_id == session.office_id,
            CounselingSession.id != session.id,
            CounselingSession.status.in_(['pending','confirmed','in_progress']),
            CounselingSession.scheduled_at < new_end
        ).all()
        conflict = None
        for c in candidates:
            c_end = c.scheduled_at + timedelta(minutes=c.duration_minutes or 60)
            if c_end > new_datetime:
                conflict = c
                break
        if conflict:
            return jsonify({'status':'error','message':'Selected time overlaps with an existing session. Please choose another slot.'}), 409
        
        # Store original datetime for notification
        original_datetime = session.scheduled_at
        
        # Update session with new datetime
        session.scheduled_at = new_datetime

        # Assign the rescheduling admin as the counselor to ensure ownership
        session.counselor_id = current_user.id

        # Auto-confirm the session upon reschedule for consistency
        session.status = 'confirmed'

        # For video sessions, ensure meeting details are generated
        if session.is_video_session and not session.meeting_id:
            session.generate_meeting_details()
        
        # Add a note about rescheduling
        if session.notes:
            session.notes += f"\n\nRescheduled: Session was moved from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')} by {current_user.get_full_name()}."
        else:
            session.notes = f"Rescheduled: Session was moved from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')} by {current_user.get_full_name()}."
        
        # Create notification for student and emit realtime update
        from app.models import Notification
        student = Student.query.get(session.student_id)
        notification = Notification(
            user_id=student.user_id,
            title="Counseling Session Rescheduled",
            message=(
                f"Your counseling session with {session.office.name if session.office else 'the office'} "
                f"has been rescheduled from {original_datetime.strftime('%Y-%m-%d %H:%M')} to {new_datetime.strftime('%Y-%m-%d %H:%M')}."
            ),
            source_office_id=session.office_id,
            is_read=False,
            link=f"/student/view-session/{session.id}",
            # Map to yellow toast via 'warning'
            notification_type="rescheduled_warning"
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
        
        # Commit DB changes and then push realtime payload
        db.session.flush()
        try:
            payload = {
                'id': getattr(notification, 'id', None),
                'title': notification.title,
                'message': notification.message,
                'notification_type': notification.notification_type,
                'source_office_id': notification.source_office_id,
                'target_office_name': session.office.name if session.office else None,
                'link': notification.link,
                'created_at': datetime.utcnow().isoformat()
            }
            push_student_notification_to_user(student.user_id, payload)
            # Also push realtime session update to reflect confirmed + new time
            try:
                push_student_session_update(student.user_id, {
                    'session_id': session.id,
                    'status': 'confirmed',
                    'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                    'is_video_session': bool(session.is_video_session),
                    'link': f"/student/view-session/{session.id}" if session.is_video_session else None
                })
            except Exception:
                pass
        except Exception:
            pass

        db.session.commit()
        
        return jsonify({
            'status': 'success', 
            'message': 'Session rescheduled successfully',
            'new_time': new_datetime.strftime('%Y-%m-%d %H:%M')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Error rescheduling session: {str(e)}'}), 500


@office_bp.route('/video-counseling/calendar-events')
@login_required
def office_calendar_events():
    """Return counseling sessions for the current office within a date range for calendar rendering."""
    if current_user.role != 'office_admin':
        return jsonify([]), 200

    office_id = current_user.office_admin.office_id
    start = request.args.get('start')
    end = request.args.get('end')

    def parse_iso(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            try:
                return datetime.strptime(s.split('T')[0], '%Y-%m-%d')
            except Exception:
                return None

    start_dt = parse_iso(start) or (datetime.utcnow() - timedelta(days=7))
    end_dt = parse_iso(end) or (datetime.utcnow() + timedelta(days=60))

    sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= start_dt,
        CounselingSession.scheduled_at <= end_dt
    ).all()

    events = []
    for s in sessions:
        dur = s.duration_minutes or 60
        e = {
            'id': s.id,
            'title': f"{('Video' if s.is_video_session else 'In-Person')} - {s.student.user.get_full_name() if s.student and s.student.user else 'Student'}",
            'start': s.scheduled_at.isoformat(),
            'end': (s.scheduled_at + timedelta(minutes=dur)).isoformat(),
            'allDay': False,
            'backgroundColor': '#3b82f6' if s.is_video_session else '#6b7280',
            'borderColor': '#2563eb' if s.is_video_session else '#4b5563',
            'textColor': '#ffffff',
            'extendedProps': {
                'status': s.status,
                'student': s.student.user.get_full_name() if s.student and s.student.user else '',
                'is_video': s.is_video_session,
                'office_id': s.office_id
            }
        }
        # Status-based color accent
        if s.status == 'pending':
            e['backgroundColor'] = '#f59e0b'
            e['borderColor'] = '#d97706'
        elif s.status == 'confirmed':
            e['backgroundColor'] = '#10b981'
            e['borderColor'] = '#059669'
        elif s.status == 'in_progress':
            e['backgroundColor'] = '#22c55e'
            e['borderColor'] = '#16a34a'
        elif s.status == 'completed':
            e['backgroundColor'] = '#9ca3af'
            e['borderColor'] = '#6b7280'
        elif s.status == 'cancelled':
            e['backgroundColor'] = '#ef4444'
            e['borderColor'] = '#dc2626'

        events.append(e)

    return jsonify(events)


@office_bp.route('/video-session/availability')
@login_required
def office_availability():
    """Return availability for the current office (office_admin) on a given date.

    Query params:
      - date: YYYY-MM-DD (required)
      - interval: slot minutes (ignored; enforced to 60)
      - start: day start HH:MM (default 08:00)
      - end: day end HH:MM (default 17:00)
      - exclude_session_id: optional session id to exclude from blocking
    """
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Unauthorized'}), 403

    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'date is required (YYYY-MM-DD)'}), 400

    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return jsonify({'error': 'invalid date format'}), 400

    office_id = current_user.office_admin.office_id

    # Force 60-minute slots regardless of input
    slot_minutes = 60

    def parse_hhmm(val, default):
        try:
            hh, mm = map(int, val.split(':'))
            return dtime(hour=hh, minute=mm)
        except Exception:
            return default

    start_param = request.args.get('start', '08:00')
    end_param = request.args.get('end', '17:00')
    start_t = parse_hhmm(start_param, dtime(8, 0))
    end_t = parse_hhmm(end_param, dtime(17, 0))

    day_start = datetime.combine(day, start_t)
    day_end = datetime.combine(day, end_t)

    exclude_id = request.args.get('exclude_session_id', type=int)

    # Blocking statuses
    blocking = ['pending', 'confirmed', 'in_progress']
    q = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.status.in_(blocking),
        CounselingSession.scheduled_at < day_end
    )
    if exclude_id:
        q = q.filter(CounselingSession.id != exclude_id)
    sessions = q.all()

    booked = []
    for s in sessions:
        s_start = s.scheduled_at
        s_end = s_start + timedelta(minutes=(s.duration_minutes or 60))
        if s_end > day_start and s_start < day_end:
            booked.append((max(s_start, day_start), min(s_end, day_end)))

    slots = []
    cursor = day_start
    now = datetime.utcnow()
    while cursor < day_end:
        slot_end = cursor + timedelta(minutes=slot_minutes)
        status = 'available'
        if slot_end <= now:
            status = 'past'
        else:
            for b_start, b_end in booked:
                if b_end > cursor and b_start < slot_end:
                    status = 'booked'
                    break
        slots.append({'time': cursor.strftime('%H:%M'), 'status': status})
        cursor = slot_end

    return jsonify({
        'office_id': office_id,
        'date': day.strftime('%Y-%m-%d'),
        'slot_interval_minutes': slot_minutes,
        'office_hours': {
            'start': start_t.strftime('%H:%M'),
            'end': end_t.strftime('%H:%M'),
        },
        'slots': slots,
    })


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


@office_bp.route('/sessions/<int:session_id>/notes', methods=['POST'])
@login_required
def update_session_notes(session_id):
    """Update session notes during or after a session"""
    if current_user.role != 'office_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    session = CounselingSession.query.get_or_404(session_id)
    
    # Check if the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Get notes from JSON request or form data
        data = request.get_json()
        notes = data.get('notes', '') if data else request.form.get('notes', '')
        
        # Update session notes
        session.notes = notes
        
        # Log activity
        AuditLog.log_action(
            actor=current_user,
            action="Updated session notes",
            target_type="counseling_session",
            status=session.status,
            is_success=True,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Notes saved successfully',
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error saving notes: {str(e)}'}), 500


@office_bp.route('/session-completed/<int:session_id>')
@login_required
def session_completed(session_id):
    """Display session completion page with summary and options"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get the session
    session = CounselingSession.query.get_or_404(session_id)
    
    # Check if the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        flash('Access denied. You do not have permission to view this session.', 'error')
        return redirect(url_for('office.video_counseling'))
    
    # Calculate session duration if session is completed
    session_duration = None
    if session.status == 'completed' and session.started_at and session.ended_at:
        duration_seconds = (session.ended_at - session.started_at).total_seconds()
        session_duration = {
            'hours': int(duration_seconds // 3600),
            'minutes': int((duration_seconds % 3600) // 60),
            'seconds': int(duration_seconds % 60)
        }
    
    # Get session statistics
    session_stats = {
        'scheduled_at': session.scheduled_at,
        'started_at': session.started_at,
        'ended_at': session.ended_at,
        'duration': session_duration,
        'meeting_link': session.meeting_link,
        'notes': session.notes or '',
        'status': session.status
    }
    
    # Get student information
    student = session.student
    
    # Get session recordings if any (placeholder for future implementation)
    recordings = []
    
    # Get related inquiries from the same student to this office
    related_inquiries = Inquiry.query.filter_by(
        student_id=session.student_id,
        office_id=session.office_id
    ).order_by(desc(Inquiry.created_at)).limit(5).all()
    
    # Get previous sessions with this student
    previous_sessions = CounselingSession.query.filter(
        CounselingSession.student_id == session.student_id,
        CounselingSession.office_id == session.office_id,
        CounselingSession.id != session_id,
        CounselingSession.status == 'completed'
    ).order_by(desc(CounselingSession.scheduled_at)).limit(5).all()
    
    # Log the view activity
    AuditLog.log_action(
        actor=current_user,
        action="Viewed session completion page",
        target_type="counseling_session",
        target_id=session_id,
        status="success",
        office=current_user.office_admin.office,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    # Get context data for the base template
    context = get_office_context()
    
    return render_template('office/session_completed.html',
                         session=session,
                         session_stats=session_stats,
                         student=student,
                         recordings=recordings,
                         related_inquiries=related_inquiries,
                         previous_sessions=previous_sessions,
                         **context)


@office_bp.route('/session-completed/<int:session_id>/download-summary', methods=['GET'])
@login_required
def download_session_summary(session_id):
    """Download session summary as PDF or text file"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    session = CounselingSession.query.get_or_404(session_id)
    
    # Check if the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Generate session summary content
    summary_content = f"""
SESSION SUMMARY
==============

Session ID: {session.id}
Student: {session.student.user.first_name} {session.student.user.last_name}
Student ID: {session.student.student_id}
Office: {session.office.name}
Counselor: {current_user.first_name} {current_user.last_name}

Session Details:
- Scheduled: {session.scheduled_at.strftime('%Y-%m-%d %H:%M:%S')}
- Started: {session.started_at.strftime('%Y-%m-%d %H:%M:%S') if session.started_at else 'N/A'}
- Ended: {session.ended_at.strftime('%Y-%m-%d %H:%M:%S') if session.ended_at else 'N/A'}
- Status: {session.status.title()}
- Type: {'Video Session' if session.is_video_session else 'In-Person Session'}

Duration: {
    f"{int((session.ended_at - session.started_at).total_seconds() // 3600)}h {int(((session.ended_at - session.started_at).total_seconds() % 3600) // 60)}m"
    if session.started_at and session.ended_at else 'N/A'
}

Session Notes:
{session.notes or 'No notes recorded'}

Meeting Link: {session.meeting_link or 'N/A'}

Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
Generated by: {current_user.first_name} {current_user.last_name}
"""
    
    # Create response
    response = Response(
        summary_content,
        mimetype='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename=session_summary_{session_id}.txt'
        }
    )
    
    # Log the download activity
    AuditLog.log_action(
        actor=current_user,
        action="Downloaded session summary",
        target_type="counseling_session",
        target_id=session_id,
        status="success",
        office=current_user.office_admin.office,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return response


@office_bp.route('/session-completed/<int:session_id>/schedule-followup', methods=['POST'])
@login_required
def schedule_followup(session_id):
    """Schedule a follow-up session"""
    if current_user.role != 'office_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    session = CounselingSession.query.get_or_404(session_id)
    
    # Check if the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        scheduled_datetime_str = data.get('scheduled_datetime')
        session_type = data.get('session_type', 'video')  # 'video' or 'in_person'
        notes = data.get('notes', '')
        
        if not scheduled_datetime_str:
            return jsonify({'success': False, 'message': 'Scheduled datetime is required'}), 400
        
        # Parse the datetime
        try:
            scheduled_datetime = datetime.fromisoformat(scheduled_datetime_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid datetime format'}), 400
        
        # Create new follow-up session
        followup_session = CounselingSession(
            student_id=session.student_id,
            office_id=session.office_id,
            scheduled_at=scheduled_datetime,
            is_video_session=(session_type == 'video'),
            status='pending',
            notes=f"Follow-up session from Session #{session.id}\n\n{notes}",
            meeting_link=str(uuid.uuid4()) if session_type == 'video' else None
        )
        
        db.session.add(followup_session)
        
        # Log activity
        AuditLog.log_action(
            actor=current_user,
            action="Scheduled follow-up session",
            target_type="counseling_session",
            target_id=followup_session.id,
            status="success",
            office=current_user.office_admin.office,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Follow-up session scheduled successfully',
            'session_id': followup_session.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error scheduling follow-up: {str(e)}'}), 500


@office_bp.route('/video-session/<int:session_id>/assign', methods=['POST'])
@login_required
def assign_counseling_session(session_id):
    """Assign the current office admin as the counselor for a session"""
    if current_user.role != 'office_admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    session = CounselingSession.query.filter_by(id=session_id).first_or_404()

    # Ensure the session belongs to the current user's office
    if session.office_id != current_user.office_admin.office_id:
        return jsonify({'status': 'error', 'message': 'You do not have permission to assign this session'}), 403

    # If already assigned to someone else, block simple assignment
    if session.counselor_id and session.counselor_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'This session is already assigned to another counselor'}), 409

    # Assign to current user
    session.counselor_id = current_user.id

    # Log the assignment
    AuditLog.log_action(
        actor=current_user,
        action="Assigned counseling session to self",
        target_type="counseling_session",
        target_id=session_id,
        status=session.status,
        office=current_user.office_admin.office,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )

    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Session assigned to you'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Failed to assign session: {str(e)}'}), 500