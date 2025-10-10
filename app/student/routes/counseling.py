from flask import render_template, redirect, url_for, flash, request, jsonify, session
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
from datetime import time as dtime

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
    
    # Get only offices that offer counseling services within student's campus
    # An office offers counseling if it either supports video OR has had counseling sessions
    campus_id = student.campus_id or session.get('selected_campus_id')
    office_query = Office.query.filter(
        or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    )
    if campus_id:
        office_query = office_query.filter(Office.campus_id == campus_id)
    offices = office_query.all()
    
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
    nature_of_concern_id = request.form.get('nature_of_concern_id')
    nature_of_concern_description = request.form.get('nature_of_concern_description')
    
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

        # Enforce campus scope (fallback to session campus)
        campus_id = student.campus_id or session.get('selected_campus_id')
        if campus_id and office.campus_id != campus_id:
            flash('You can only schedule counseling with offices in your campus.', 'error')
            return redirect(url_for('student.request_counseling_session'))
        
        # If video session is requested, verify office supports it
        if is_video and not office.supports_video:
            flash('The selected office does not support video counseling', 'error')
            return redirect(url_for('student.request_counseling_session'))

        # Validate selected nature_of_concern belongs to this office's counseling concern set
        if nature_of_concern_id:
            assoc = OfficeConcernType.query.filter_by(
                office_id=office.id,
                concern_type_id=int(nature_of_concern_id),
                for_counseling=True
            ).first()
            if not assoc:
                flash('Selected concern type is not available for counseling in the chosen office.', 'error')
                return redirect(url_for('student.request_counseling_session'))
        
        # Prevent double-booking ONLY against confirmed sessions per policy
        # Note: pending or in-progress requests should not block new requests.
        duration_minutes = 60  # default; can later be dynamic per office/session
        requested_end = scheduled_datetime + timedelta(minutes=duration_minutes)
        conflicts = CounselingSession.query.filter(
            CounselingSession.office_id == office.id,
            CounselingSession.status.in_(['confirmed']),
            CounselingSession.scheduled_at < requested_end
        ).all()
        for c in conflicts:
            c_end = c.scheduled_at + timedelta(minutes=(c.duration_minutes or 60))
            if c_end > scheduled_datetime:
                flash('The selected time overlaps with a confirmed session for this office. Please choose a different slot.', 'error')
                return redirect(url_for('student.request_counseling_session'))

        # Create new counseling session without assigning a counselor - this will be done by office admin
        new_session = CounselingSession(
            student_id=student.id,
            office_id=office_id,
            scheduled_at=scheduled_datetime,
            status='pending',
            is_video_session=is_video,
            notes=notes,
            nature_of_concern_id=int(nature_of_concern_id) if nature_of_concern_id else None,
            nature_of_concern_description=nature_of_concern_description or None,
            # counselor_id will be assigned when an office admin confirms the session
        )
        
        db.session.add(new_session)
        db.session.flush()  # Get the session ID
        
        # Create smart notifications for office admins
        from app.utils.smart_notifications import SmartNotificationManager
        office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(office_id)
        
        for admin_user_id in office_admin_user_ids:
            SmartNotificationManager.create_counseling_notification(
                new_session, admin_user_id, 'new_counseling_request'
            )
        
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
    
    # Get only offices that offer counseling services, scoped to student's campus
    # An office offers counseling if it either supports video OR has had counseling sessions
    campus_id = student.campus_id or session.get('selected_campus_id')
    office_query = Office.query.filter(
        or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    )
    if campus_id:
        office_query = office_query.filter(Office.campus_id == campus_id)
    offices = office_query.all()
    
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
    
    # Load ONLY concern types that are enabled for counseling (for_counseling=True)
    # within the scoped counseling offices. This excludes inquiry-only concern types.
    concern_types = []
    concern_type_office_map = {}
    if counseling_offices:
        office_ids = [o.id for o in counseling_offices]
        ct_rows = (
            db.session.query(ConcernType, OfficeConcernType.office_id)
            .join(OfficeConcernType, ConcernType.id == OfficeConcernType.concern_type_id)
            .filter(OfficeConcernType.office_id.in_(office_ids), OfficeConcernType.for_counseling.is_(True))
            .order_by(ConcernType.name)
            .all()
        )
        seen = {}
        for ct, oid in ct_rows:
            if ct.id not in seen:
                concern_types.append(ct)
                seen[ct.id] = ct
            concern_type_office_map.setdefault(ct.id, set()).add(oid)
    concern_type_office_map = {k: sorted(list(v)) for k, v in concern_type_office_map.items()}

    return render_template(
        'student/request_counseling.html',
        offices=offices,
        counseling_offices_count=counseling_offices_count,
        today=today,
        max_date=max_date,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
    concern_types=concern_types,
    concern_type_office_map=concern_type_office_map
    )

@student_bp.route('/office/<int:office_id>/availability')
@login_required
@role_required(['student'])
def office_availability(office_id):
    """Return availability for an office on a given date.

    Query params:
      - date: YYYY-MM-DD (required)
      - interval: slot minutes (default 30)
      - start: office day start HH:MM (default 08:00)
      - end: office day end HH:MM (default 17:00)

    Returns only slot statuses (available/booked/past). No sensitive details.
    """
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'date is required (YYYY-MM-DD)'}), 400

    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'invalid date format'}), 400

    # Validate student and office campus scope
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    office = Office.query.get_or_404(office_id)
    campus_id = student.campus_id or session.get('selected_campus_id')
    if campus_id and office.campus_id != campus_id:
        return jsonify({'error': 'office not accessible'}), 403

    # Interpret working window
    # Enforce 1-hour slots by default for scheduling UI
    interval = request.args.get('interval', default='60')
    try:
        slot_minutes = 60 if int(interval) != 60 else 60
    except (TypeError, ValueError):
        slot_minutes = 60

    def parse_hhmm(val, default):
        try:
            hh, mm = map(int, val.split(':'))
            return dtime(hour=hh, minute=mm)
        except Exception:
            return default

    # Default office hours: 08:00–17:00 unless overridden by query params
    start_param = request.args.get('start', '08:00')
    end_param = request.args.get('end', '17:00')
    start_t = parse_hhmm(start_param, dtime(8, 0))
    end_t = parse_hhmm(end_param, dtime(17, 0))

    # Build datetime range for the day
    day_start = datetime.combine(day, start_t)
    day_end = datetime.combine(day, end_t)

    # Fetch overlapping sessions for that office and day
    # Only CONFIRMED sessions should block time slots
    blocking_statuses = ['confirmed']
    sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office.id,
        CounselingSession.status.in_(blocking_statuses),
        CounselingSession.scheduled_at < day_end
    ).all()

    # Prepare booked intervals (start, end) for that day only
    booked_intervals = []
    for s in sessions:
        s_start = s.scheduled_at
        s_end = s_start + timedelta(minutes=(s.duration_minutes or 60))
        # Keep if overlaps the [day_start, day_end) interval
        if s_end > day_start and s_start < day_end:
            # Clamp to the day window to avoid leaking exact bounds outside the day
            seg_start = max(s_start, day_start)
            seg_end = min(s_end, day_end)
            booked_intervals.append((seg_start, seg_end))

    # Generate slots and mark statuses
    slots = []
    cursor = day_start
    now = datetime.utcnow()
    while cursor < day_end:
        slot_end = cursor + timedelta(minutes=slot_minutes)
        # Determine status
        status = 'available'
        # Past check (relative to UTC app time)
        if slot_end <= now:
            status = 'past'
        else:
            for b_start, b_end in booked_intervals:
                if b_end > cursor and b_start < slot_end:
                    status = 'booked'
                    break

        slots.append({
            'time': cursor.strftime('%H:%M'),
            'status': status
        })
        cursor = slot_end

    return jsonify({
        'office_id': office.id,
        'date': day.strftime('%Y-%m-%d'),
        'slot_interval_minutes': slot_minutes,
        'office_hours': {
            'start': start_t.strftime('%H:%M'),
            'end': end_t.strftime('%H:%M')
        },
        'slots': slots
    })

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
    # Get only offices that offer counseling services for dropdown and cards, scoped to student's campus
    campus_id = student.campus_id or session.get('selected_campus_id')
    offices_query = Office.query.filter(
        or_(
            Office.supports_video == True,
            Office.counseling_sessions.any()
        )
    )
    if campus_id:
        offices_query = offices_query.filter(Office.campus_id == campus_id)
    offices = offices_query.all()
    
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