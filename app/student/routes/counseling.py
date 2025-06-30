from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import desc, or_
from app.student import student_bp
from app.models import (
    CounselingSession, Student, User, Office, 
    StudentActivityLog, Notification, OfficeConcernType, ConcernType,
    SessionParticipation
)
from app.extensions import db
from app.utils import role_required

@student_bp.route('/counseling-sessions')
@login_required
@role_required(['student'])
def counseling_sessions():
    """View all counseling sessions for the student"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get all sessions for this student
    sessions = CounselingSession.query.filter_by(
        student_id=student.id    ).order_by(desc(CounselingSession.scheduled_at)).all()
    
    # Get only offices that offer counseling services
    # An office offers counseling if it either supports video OR has had counseling sessions
    offices = Office.query.filter(
        or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    ).all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed counseling sessions",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    # Calculate which sessions can be joined (within 15 minutes of scheduled time)
    now = datetime.utcnow()
    joinable_sessions = set()
    for session in sessions:
        if (session.status == 'confirmed' and session.is_video_session and 
            session.scheduled_at <= now + timedelta(minutes=15) and 
            session.scheduled_at >= now - timedelta(minutes=15)):
            joinable_sessions.add(session.id)
    
    return render_template(
        'student/counseling_sessions.html',
        sessions=sessions,
        offices=offices,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        now=now,
        joinable_sessions=joinable_sessions,
        timedelta=timedelta
    )

@student_bp.route('/view-session/<int:session_id>')
@login_required
@role_required(['student'])
def view_session(session_id):
    """View details for a specific counseling session"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the session and verify ownership
    session = CounselingSession.query.filter_by(
        id=session_id,
        student_id=student.id
    ).first_or_404()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Viewed counseling session #{session_id}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    # Placeholder - return a simple template
    return render_template(
        'student/view_session.html',
        session=session,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

@student_bp.route('/schedule-session', methods=['POST'])
@login_required
@role_required(['student'])
def schedule_session():
    """Schedule a new counseling session"""
    # Get form data
    office_id = request.form.get('office_id')
    scheduled_date = request.form.get('scheduled_date')
    scheduled_time = request.form.get('scheduled_time')
    is_video = request.form.get('is_video') == 'true'  # Handle string value 'true' vs 'false'
    notes = request.form.get('notes', '')
    
    # Validate required fields
    if not office_id or not scheduled_date or not scheduled_time:
        flash('Please fill all required fields', 'error')
        return redirect(url_for('student.request_counseling_session'))
    
    try:
        # Parse the date and time
        scheduled_datetime = datetime.strptime(f"{scheduled_date} {scheduled_time}", '%Y-%m-%d %H:%M')
        
        # Ensure the appointment is in the future
        if scheduled_datetime <= datetime.utcnow():
            flash('Appointment must be scheduled for a future date and time', 'error')
            return redirect(url_for('student.request_counseling_session'))
        
        # Get the student record
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        
        # Verify the office exists
        office = Office.query.get_or_404(office_id)
        
        # If video session is requested, verify office supports it
        if is_video and not office.supports_video:
            flash('The selected office does not support video counseling', 'error')
            return redirect(url_for('student.request_counseling_session'))
        
        # Create new counseling session without assigning a counselor - this will be done by office admin
        new_session = CounselingSession(
            student_id=student.id,
            office_id=office_id,
            scheduled_at=scheduled_datetime,
            status='pending',
            is_video_session=is_video,
            notes=notes,
            # counselor_id will be assigned when an office admin confirms the session
        )
        
        db.session.add(new_session)
        
        # Log this activity
        log_entry = StudentActivityLog(
            student_id=student.id,
            action="Scheduled new counseling session",
            related_id=new_session.id,
            related_type="counseling_session",
            timestamp=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        db.session.add(log_entry)
        
        db.session.commit()
        flash('Counseling session requested successfully. An office administrator will review and confirm your request.', 'success')
        return redirect(url_for('student.view_session', session_id=new_session.id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error scheduling session: {str(e)}', 'error')
        return redirect(url_for('student.request_counseling_session'))

@student_bp.route('/request-counseling-session')
@login_required
@role_required(['student'])
def request_counseling_session():
    """Display form to request a new counseling session"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get only offices that offer counseling services
    # An office offers counseling if it either supports video OR has had counseling sessions  
    offices = Office.query.filter(
        or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    ).all()
    
    # Filter offices that can offer counseling (either video or in-person)
    # All offices in the filtered list above already offer counseling services
    counseling_offices = offices
    counseling_offices_count = len(counseling_offices)
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Get date constraints for the form
    today = datetime.utcnow().date().strftime('%Y-%m-%d')
    max_date = (datetime.utcnow() + timedelta(days=30)).date().strftime('%Y-%m-%d')
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed counseling session request form",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/request_counseling.html',
        offices=offices,
        counseling_offices_count=counseling_offices_count,
        today=today,
        max_date=max_date,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

@student_bp.route('/office/<int:office_id>/check-video-support')
@login_required
@role_required(['student'])
def check_office_video_support(office_id):
    """API endpoint to check if an office supports video counseling"""
    office = Office.query.get_or_404(office_id)
    
    # Log this API call
    student = Student.query.filter_by(user_id=current_user.id).first()
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Checked video support for office: {office.name}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return jsonify({
        'supports_video': office.supports_video,
        'office_name': office.name
    })

@student_bp.route('/cancel-session/<int:session_id>', methods=['POST'])
@login_required
@role_required(['student'])
def cancel_session(session_id):
    """Cancel a scheduled counseling session"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the session and verify ownership
    session = CounselingSession.query.filter_by(
        id=session_id,
        student_id=student.id
    ).first_or_404()
    
    # Only allow cancellation if the session is pending or confirmed
    if session.status not in ['pending', 'confirmed']:
        flash('This session cannot be cancelled.', 'error')
        return redirect(url_for('student.view_session', session_id=session_id))
    
    # Get the reason for cancellation
    reason = request.form.get('reason', 'No reason provided')
    
    try:
        # Update session status
        session.status = 'cancelled'
        
        # Add cancellation reason to notes
        if session.notes:
            session.notes += f"\n\nCancellation reason: {reason}"
        else:
            session.notes = f"Cancellation reason: {reason}"
        
        # Log this activity
        log_entry = StudentActivityLog(
            student_id=student.id,
            action=f"Cancelled counseling session #{session_id}",
            related_id=session.id,
            related_type="counseling_session",
            timestamp=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        db.session.add(log_entry)
        
        db.session.commit()
        flash('Counseling session cancelled successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling session: {str(e)}', 'error')
    
    return redirect(url_for('student.counseling_sessions'))

@student_bp.route('/request-recording/<int:session_id>', methods=['POST'])
@login_required
@role_required(['student'])
def request_recording(session_id):
    """Request a recording of a completed video counseling session"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the session and verify ownership
    session = CounselingSession.query.filter_by(
        id=session_id,
        student_id=student.id
    ).first_or_404()
    
    # Only allow recording requests for completed video sessions
    if not session.is_video_session or session.status != 'completed':
        return jsonify({
            'success': False,
            'message': 'Recording can only be requested for completed video sessions.'
        })
    
    try:
        # Check if there's already a recording
        from app.models import SessionRecording, Notification
        recording = SessionRecording.query.filter_by(session_id=session_id).first()
        
        if recording:
            # Recording exists, create a notification for the student
            notification = Notification(
                user_id=current_user.id,
                title="Recording Available",
                message=f"The recording for your counseling session on {session.scheduled_at.strftime('%Y-%m-%d')} is available.",
                source_office_id=session.office_id,
                inquiry_id=None,
                announcement_id=None,
                is_read=False
            )
            db.session.add(notification)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Recording is available. Check your notifications.'
            })
        
        # No recording found, notify the office about the request
        notification = Notification(
            user_id=session.counselor_id,
            title="Recording Request",
            message=f"Student {student.user.get_full_name()} has requested the recording of their counseling session on {session.scheduled_at.strftime('%Y-%m-%d')}.",
            is_read=False
        )
        db.session.add(notification)
        
        # Log this activity
        log_entry = StudentActivityLog(
            student_id=student.id,
            action=f"Requested recording for counseling session #{session_id}",
            related_id=session.id,
            related_type="counseling_session",
            timestamp=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        db.session.add(log_entry)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Recording request sent successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error requesting recording: {str(e)}'
        })

@student_bp.route('/video-session/<int:session_id>')
@login_required
@role_required(['student'])
def join_video_session(session_id):
    """Join a video counseling session"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the session and verify ownership
    session = CounselingSession.query.filter_by(
        id=session_id,
        student_id=student.id,
        is_video_session=True
    ).first_or_404()
    
    # Check if session is already completed
    if session.status == 'completed':
        flash('This session has already been completed. You can still view the details.', 'info')
        return redirect(url_for('student.view_session', session_id=session_id))
    
    # Check if session is cancelled
    if session.status == 'cancelled':
        flash('This session has been cancelled.', 'warning')
        return redirect(url_for('student.view_session', session_id=session_id))
    
    # Get counselor information if assigned
    counselor = User.query.get(session.counselor_id) if session.counselor_id else None
    
    # If session doesn't have meeting details, generate them
    if not session.meeting_id:
        session.generate_meeting_details()
        db.session.commit()
    
    # Update the session status if not already in progress, completed, or cancelled
    now = datetime.utcnow()
    if session.status not in ['in_progress', 'completed', 'cancelled']:
        session.student_joined_at = now
        session.status = 'in_progress'
        
        # Create participation record
        participation = SessionParticipation(
            session_id=session_id,
            user_id=current_user.id,
            joined_at=now,
            device_info=request.user_agent.string,
            ip_address=request.remote_addr
        )
        db.session.add(participation)
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action=f"Joined video session #{session_id}",
        related_id=session.id,
        related_type="counseling_session",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    return render_template(
        'student/video_session.html',
        session=session,
        counselor=counselor,
        meeting_id=session.meeting_id,
        meeting_url=session.meeting_url,
        meeting_password=session.meeting_password,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )

@student_bp.route('/counseling-dashboard')
@login_required
@role_required(['student'])
def counseling_dashboard():
    """Enhanced dashboard view for counseling sessions with statistics and filtering"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    office_filter = request.args.get('office_id', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Base query for sessions
    sessions_query = CounselingSession.query.filter_by(student_id=student.id)
    
    # Apply status filter
    if status_filter != 'all':
        sessions_query = sessions_query.filter_by(status=status_filter)
    
    # Apply office filter
    if office_filter != 'all':
        sessions_query = sessions_query.filter_by(office_id=int(office_filter))
    
    # Get paginated sessions ordered by date
    sessions_pagination = sessions_query.order_by(
        desc(CounselingSession.scheduled_at)
    ).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Calculate statistics
    all_sessions = CounselingSession.query.filter_by(student_id=student.id).all()
    stats = {
        'total': len(all_sessions),
        'pending': len([s for s in all_sessions if s.status == 'pending']),
        'confirmed': len([s for s in all_sessions if s.status == 'confirmed']),
        'completed': len([s for s in all_sessions if s.status == 'completed']),
        'cancelled': len([s for s in all_sessions if s.status == 'cancelled']),
        'no_show': len([s for s in all_sessions if s.status == 'no-show']),
        'in_progress': len([s for s in all_sessions if s.status == 'in_progress']),
        'upcoming': len([s for s in all_sessions if s.status in ['pending', 'confirmed'] and s.scheduled_at > datetime.utcnow()])
    }
      # Get only offices that offer counseling services for dropdown filter
    offices = Office.query.filter(
        db.or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    ).all()
    
    # Get unread notifications count for navbar
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    # Get notifications for dropdown  
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()
    
    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed counseling dashboard",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    # Calculate which sessions can be joined (within 15 minutes of scheduled time)
    now = datetime.utcnow()
    joinable_sessions = set()
    for session in sessions_pagination.items:
        if (session.status == 'confirmed' and session.is_video_session and 
            session.scheduled_at <= now + timedelta(minutes=15) and 
            session.scheduled_at >= now - timedelta(minutes=15)):
            joinable_sessions.add(session.id)
    
    return render_template(
        'student/counseling_dashboard.html',
        sessions=sessions_pagination.items,
        pagination=sessions_pagination,
        stats=stats,
        offices=offices,
        current_status=status_filter,
        current_office=office_filter,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        now=now,
        joinable_sessions=joinable_sessions,
        timedelta=timedelta
    )