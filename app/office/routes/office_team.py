from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, Notification
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, case, desc, or_
from app.office import office_bp

# Import the office context function
from app.office.routes.office_dashboard import get_office_context

@office_bp.route('/team-dashboard')
@login_required
def team_dashboard():
    """View comprehensive team dashboard for the office"""
    if current_user.role != 'office_admin':
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    
    # Get all staff members for this office
    staff_members = User.query.join(OfficeAdmin).filter(
        OfficeAdmin.office_id == office_id,
        User.role == 'office_admin'
    ).all()
    
    # Get activity stats for each staff member
    staff_data = []
    now = datetime.utcnow()
    one_month_ago = now - timedelta(days=30)
    today_start = datetime.combine(now.date(), datetime.min.time())
    
    # Get office information
    office = Office.query.get(office_id)
    
    # Calculate overall office metrics
    total_inquiries = Inquiry.query.filter_by(office_id=office_id).count()
    pending_inquiries = Inquiry.query.filter_by(office_id=office_id, status='pending').count()
    in_progress_inquiries = Inquiry.query.filter_by(office_id=office_id, status='in_progress').count()
    resolved_inquiries = Inquiry.query.filter_by(office_id=office_id, status='resolved').count()
    
    total_sessions = CounselingSession.query.filter_by(office_id=office_id).count()
    upcoming_sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.status.in_(['pending', 'confirmed']),
        CounselingSession.scheduled_at > now
    ).count()
    completed_sessions = CounselingSession.query.filter_by(
        office_id=office_id, 
        status='completed'
    ).count()
    
    # Get activity data for each staff member
    for staff in staff_members:
        # Count inquiries handled (both pending and resolved)
        inquiries_handled = Inquiry.query.filter(
            Inquiry.office_id == office_id,
            # Check if the staff member handled any messages for this inquiry
            Inquiry.id.in_(
                db.session.query(InquiryMessage.inquiry_id)
                .filter(InquiryMessage.sender_id == staff.id)
                .distinct()
            )
        ).count()
        
        # Count resolved inquiries
        inquiries_resolved = Inquiry.query.filter(
            Inquiry.office_id == office_id,
            Inquiry.status == 'resolved',
            # Check if the staff member handled any messages for this inquiry
            Inquiry.id.in_(
                db.session.query(InquiryMessage.inquiry_id)
                .filter(InquiryMessage.sender_id == staff.id)
                .distinct()
            )
        ).count()
        
        # Count pending inquiries being handled
        inquiries_pending = Inquiry.query.filter(
            Inquiry.office_id == office_id,
            Inquiry.status.in_(['pending', 'in_progress']),
            # Check if the staff member handled any messages for this inquiry
            Inquiry.id.in_(
                db.session.query(InquiryMessage.inquiry_id)
                .filter(InquiryMessage.sender_id == staff.id)
                .distinct()
            )
        ).count()
        
        # Calculate response time (average minutes to first response)
        avg_response_time = db.session.query(
            func.avg(
                func.extract('epoch', InquiryMessage.created_at) - 
                func.extract('epoch', Inquiry.created_at)
            ) / 60  # Convert seconds to minutes
        ).join(
            Inquiry, InquiryMessage.inquiry_id == Inquiry.id
        ).filter(
            Inquiry.office_id == office_id,
            InquiryMessage.sender_id == staff.id,
            # Only first response from staff to each inquiry
            ~InquiryMessage.id.in_(
                db.session.query(func.min(InquiryMessage.id))
                .filter(InquiryMessage.sender_id == staff.id)
                .group_by(InquiryMessage.inquiry_id)
            )
        ).scalar() or 0
        
        # Count counseling sessions conducted
        sessions_count = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.status == 'completed'
        ).count()
        
        # Count upcoming sessions
        upcoming_sessions_count = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.status.in_(['pending', 'confirmed']),
            CounselingSession.scheduled_at > now
        ).count()
        
        # Get today's sessions
        todays_sessions_count = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.scheduled_at >= today_start,
            CounselingSession.scheduled_at < today_start + timedelta(days=1)
        ).count()
        
        # Get last login time
        last_login = OfficeLoginLog.query.filter_by(
            office_admin_id=staff.office_admin.id
        ).order_by(desc(OfficeLoginLog.login_time)).first()
        
        # Activity breakdown for last 30 days
        monthly_inquiries = db.session.query(
            func.count(InquiryMessage.id)
        ).filter(
            InquiryMessage.sender_id == staff.id,
            InquiryMessage.created_at > one_month_ago
        ).scalar() or 0
        
        monthly_sessions = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.scheduled_at > one_month_ago
        ).count()
        
        # Calculate workload level
        total_active_items = inquiries_pending + upcoming_sessions_count
        if total_active_items < 3:
            workload = "low"
        elif total_active_items < 7:
            workload = "medium"
        else:
            workload = "high"
        
        staff_data.append({
            'user': staff,
            'inquiries_handled': inquiries_handled,
            'inquiries_resolved': inquiries_resolved,
            'inquiries_pending': inquiries_pending,
            'sessions_count': sessions_count,
            'upcoming_sessions': upcoming_sessions_count,
            'todays_sessions': todays_sessions_count,
            'total_activity': inquiries_handled + sessions_count,
            'monthly_activity': monthly_inquiries + monthly_sessions,
            'avg_response_time': int(avg_response_time) if avg_response_time else 0,
            'last_login': last_login.login_time if last_login else None,
            'is_online': staff.is_online and staff.last_activity > now - timedelta(minutes=15),
            'workload': workload
        })
    
    # Sort by activity
    staff_data.sort(key=lambda x: x['is_online'], reverse=True)
    
    # Get latest activity logs
    activity_logs = AuditLog.query.join(
        User, AuditLog.actor_id == User.id
    ).join(
        OfficeAdmin, User.id == OfficeAdmin.user_id
    ).filter(
        OfficeAdmin.office_id == office_id
    ).order_by(
        AuditLog.timestamp.desc()
    ).limit(10).all()
    
    # Get recent announcements
    recent_announcements = []
    # Add code to get announcements if needed
    
    # Get context data for shared navigation/sidebar
    context = get_office_context()
    context.update({
        'staff_data': staff_data,
        'office': office,
        'total_inquiries': total_inquiries,
        'pending_inquiries': pending_inquiries,
        'in_progress_inquiries': in_progress_inquiries,
        'resolved_inquiries': resolved_inquiries,
        'total_sessions': total_sessions,
        'upcoming_sessions': upcoming_sessions,
        'completed_sessions': completed_sessions,
        'activity_logs': activity_logs,
        'recent_announcements': recent_announcements
    })
    
    return render_template('office/team_dashboard.html', **context)

@office_bp.route('/api/team-data')
@login_required
def team_data():
    """API endpoint to get updated team data for AJAX refreshes"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Get all staff members for this office
    staff_members = User.query.join(OfficeAdmin).filter(
        OfficeAdmin.office_id == office_id,
        User.role == 'office_admin'
    ).all()
    
    # Build simplified staff data for JSON response
    now = datetime.utcnow()
    staff_data = []
    
    for staff in staff_members:
        staff_data.append({
            'id': staff.id,
            'name': staff.get_full_name(),
            'is_online': staff.is_online and staff.last_activity > now - timedelta(minutes=15),
            'last_activity': staff.last_activity.isoformat() if staff.last_activity else None
        })
    
    # Get overall office metrics
    pending_inquiries = Inquiry.query.filter_by(office_id=office_id, status='pending').count()
    in_progress_inquiries = Inquiry.query.filter_by(office_id=office_id, status='in_progress').count()
    
    return jsonify({
        'staff_data': staff_data,
        'pending_inquiries': pending_inquiries,
        'in_progress_inquiries': in_progress_inquiries,
        'timestamp': datetime.utcnow().isoformat()
    })

@office_bp.route('/api/pending-inquiries')
@login_required
def pending_inquiries():
    """API endpoint to get pending inquiries for assignment"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Get all pending and in-progress inquiries for this office
    inquiries = Inquiry.query.filter(
        Inquiry.office_id == office_id,
        Inquiry.status.in_(['pending', 'in_progress'])
    ).order_by(desc(Inquiry.created_at)).all()
    
    # Build simplified inquiry data for JSON response
    inquiry_data = []
    for inquiry in inquiries:
        inquiry_data.append({
            'id': inquiry.id,
            'subject': inquiry.subject,
            'status': inquiry.status,
            'created_at': inquiry.created_at.isoformat()
        })
    
    return jsonify({
        'inquiries': inquiry_data
    })

@office_bp.route('/api/reassign-inquiry', methods=['POST'])
@login_required
def reassign_inquiry():
    """API endpoint to reassign an inquiry to another staff member"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    inquiry_id = request.json.get('inquiry_id')
    staff_id = request.json.get('staff_id')
    
    if not inquiry_id or not staff_id:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    # Verify the staff member belongs to the same office
    office_id = current_user.office_admin.office_id
    staff_exists = User.query.join(OfficeAdmin).filter(
        User.id == staff_id,
        OfficeAdmin.office_id == office_id
    ).first()
    
    if not staff_exists:
        return jsonify({'error': 'Staff member not found or not in this office'}), 404
    
    # Update the inquiry assignment
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_id).first()
    if not inquiry:
        return jsonify({'error': 'Inquiry not found or not in this office'}), 404
    
    # Log the reassignment
    log = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action=f"Reassigned inquiry #{inquiry_id} to {staff_exists.get_full_name()}",
        target_type='inquiry',
        inquiry_id=inquiry_id,
        office_id=office_id
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@office_bp.route('/api/update-staff-status', methods=['POST'])
@login_required
def update_staff_status():
    """API endpoint to update staff status manually"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    status = request.json.get('status')
    
    if not status or status not in ['online', 'away', 'busy', 'offline']:
        return jsonify({'error': 'Invalid status'}), 400
    
    # Update user status
    current_user.is_online = status in ['online', 'away', 'busy']
    current_user.last_activity = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True})

@office_bp.route('/dashboard_data')
@login_required
def team_dashboard_redirect():
    """Compatibility redirect to team dashboard"""
    return redirect(url_for('office.team_dashboard'))

@office_bp.route('/api/team-performance-metrics')
@login_required
def team_performance_metrics():
    """API endpoint to get detailed team performance metrics"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Get date range from request
    days = request.args.get('days', 30, type=int)
    date_from = datetime.utcnow() - timedelta(days=days)
    
    # Get staff members
    staff_members = User.query.join(OfficeAdmin).filter(
        OfficeAdmin.office_id == office_id,
        User.role == 'office_admin'
    ).all()
    
    performance_data = []
    
    for staff in staff_members:
        # Get performance metrics for the specified period
        inquiry_responses = db.session.query(
            func.count(InquiryMessage.id),
            func.avg(
                func.extract('epoch', InquiryMessage.created_at) - 
                func.extract('epoch', Inquiry.created_at)
            ) / 60  # Average response time in minutes
        ).join(
            Inquiry, InquiryMessage.inquiry_id == Inquiry.id
        ).filter(
            Inquiry.office_id == office_id,
            InquiryMessage.sender_id == staff.id,
            InquiryMessage.created_at >= date_from
        ).first()
        
        # Get session completion rate
        total_sessions = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.created_at >= date_from
        ).count()
        
        completed_sessions = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.status == 'completed',
            CounselingSession.created_at >= date_from
        ).count()
        
        # Get student satisfaction (if available)
        # You can implement a rating system later
        satisfaction_rating = 4.5  # Placeholder
        
        performance_data.append({
            'staff_id': staff.id,
            'name': staff.get_full_name(),
            'profile_pic': staff.profile_pic,
            'responses_count': inquiry_responses[0] or 0,
            'avg_response_time': int(inquiry_responses[1] or 0),
            'total_sessions': total_sessions,
            'completed_sessions': completed_sessions,
            'completion_rate': (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0,
            'satisfaction_rating': satisfaction_rating,
            'is_online': staff.is_online and staff.last_activity > datetime.utcnow() - timedelta(minutes=15)
        })
    
    return jsonify({
        'performance_data': performance_data,
        'period_days': days,
        'timestamp': datetime.utcnow().isoformat()
    })

@office_bp.route('/api/team-workload-analytics')
@login_required
def team_workload_analytics():
    """API endpoint to get detailed workload analytics"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    now = datetime.utcnow()
    
    # Get workload distribution
    staff_members = User.query.join(OfficeAdmin).filter(
        OfficeAdmin.office_id == office_id,
        User.role == 'office_admin'
    ).all()
    
    workload_data = []
    total_pending = 0
    total_upcoming = 0
    
    for staff in staff_members:
        # Get current workload
        pending_inquiries = Inquiry.query.filter(
            Inquiry.office_id == office_id,
            Inquiry.status.in_(['pending', 'in_progress']),
            Inquiry.id.in_(
                db.session.query(InquiryMessage.inquiry_id)
                .filter(InquiryMessage.sender_id == staff.id)
                .distinct()
            )
        ).count()
        
        upcoming_sessions = CounselingSession.query.filter(
            CounselingSession.office_id == office_id,
            CounselingSession.counselor_id == staff.id,
            CounselingSession.status.in_(['pending', 'confirmed']),
            CounselingSession.scheduled_at > now
        ).count()
        
        total_workload = pending_inquiries + upcoming_sessions
        total_pending += pending_inquiries
        total_upcoming += upcoming_sessions
        
        # Determine workload level
        if total_workload < 3:
            workload_level = "low"
            workload_color = "green"
        elif total_workload < 7:
            workload_level = "medium"
            workload_color = "yellow"
        else:
            workload_level = "high"
            workload_color = "red"
        
        workload_data.append({
            'staff_id': staff.id,
            'name': staff.get_full_name(),
            'pending_inquiries': pending_inquiries,
            'upcoming_sessions': upcoming_sessions,
            'total_workload': total_workload,
            'workload_level': workload_level,
            'workload_color': workload_color,
            'availability_score': max(0, 100 - (total_workload * 10))  # Simple availability score
        })
    
    # Calculate office-wide metrics
    workload_distribution = {
        'low': len([w for w in workload_data if w['workload_level'] == 'low']),
        'medium': len([w for w in workload_data if w['workload_level'] == 'medium']),
        'high': len([w for w in workload_data if w['workload_level'] == 'high'])
    }
    
    return jsonify({
        'workload_data': workload_data,
        'workload_distribution': workload_distribution,
        'total_pending_inquiries': total_pending,
        'total_upcoming_sessions': total_upcoming,
        'timestamp': datetime.utcnow().isoformat()
    })

@office_bp.route('/api/team-activity-timeline')
@login_required
def team_activity_timeline():
    """API endpoint to get team activity timeline for the last 24 hours"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    office_id = current_user.office_admin.office_id
    now = datetime.utcnow()
    twenty_four_hours_ago = now - timedelta(hours=24)
    
    # Get activity logs for the office
    activity_logs = AuditLog.query.join(
        User, AuditLog.actor_id == User.id
    ).join(
        OfficeAdmin, User.id == OfficeAdmin.user_id
    ).filter(
        OfficeAdmin.office_id == office_id,
        AuditLog.timestamp >= twenty_four_hours_ago
    ).order_by(
        AuditLog.timestamp.desc()
    ).limit(50).all()
    
    # Get recent inquiry messages
    recent_messages = InquiryMessage.query.join(
        Inquiry, InquiryMessage.inquiry_id == Inquiry.id
    ).join(
        User, InquiryMessage.sender_id == User.id
    ).filter(
        Inquiry.office_id == office_id,
        User.role == 'office_admin',
        InquiryMessage.created_at >= twenty_four_hours_ago
    ).order_by(
        InquiryMessage.created_at.desc()
    ).limit(30).all()
    
    # Get recent sessions
    recent_sessions = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        or_(
            CounselingSession.created_at >= twenty_four_hours_ago,
            CounselingSession.scheduled_at >= twenty_four_hours_ago
        )
    ).order_by(
        CounselingSession.created_at.desc()
    ).limit(20).all()
    
    # Combine and format timeline data
    timeline_data = []
    
    # Add audit logs
    for log in activity_logs:
        timeline_data.append({
            'type': 'audit_log',
            'timestamp': log.timestamp.isoformat(),
            'actor': log.actor.get_full_name() if log.actor else 'System',
            'action': log.action,
            'details': log.details or '',
            'icon': 'fas fa-clipboard-list',
            'color': 'blue'
        })
    
    # Add message responses
    for message in recent_messages:
        timeline_data.append({
            'type': 'inquiry_response',
            'timestamp': message.created_at.isoformat(),
            'actor': message.sender.get_full_name(),
            'action': f'Responded to inquiry: {message.inquiry.subject}',
            'details': f'Message length: {len(message.content)} characters',
            'icon': 'fas fa-reply',
            'color': 'green'
        })
    
    # Add session activities
    for session in recent_sessions:
        counselor_name = session.counselor.get_full_name() if session.counselor else 'Unassigned'
        timeline_data.append({
            'type': 'counseling_session',
            'timestamp': session.created_at.isoformat(),
            'actor': counselor_name,
            'action': f'Session {session.status}: {session.session_type}',
            'details': f'Scheduled for {session.scheduled_at.strftime("%Y-%m-%d %H:%M")}',
            'icon': 'fas fa-video',
            'color': 'purple'
        })
    
    # Sort by timestamp (most recent first)
    timeline_data.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify({
        'timeline_data': timeline_data[:30],  # Limit to 30 most recent
        'timestamp': now.isoformat()
    })

@office_bp.route('/api/assign-inquiry', methods=['POST'])
@login_required
def assign_inquiry():
    """API endpoint to assign an unassigned inquiry to a staff member"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    inquiry_id = request.json.get('inquiry_id')
    staff_id = request.json.get('staff_id')
    
    if not inquiry_id or not staff_id:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    office_id = current_user.office_admin.office_id
    
    # Verify the staff member belongs to the same office
    staff = User.query.join(OfficeAdmin).filter(
        User.id == staff_id,
        OfficeAdmin.office_id == office_id
    ).first()
    
    if not staff:
        return jsonify({'error': 'Staff member not found'}), 404
    
    # Verify the inquiry belongs to this office
    inquiry = Inquiry.query.filter_by(id=inquiry_id, office_id=office_id).first()
    if not inquiry:
        return jsonify({'error': 'Inquiry not found'}), 404
    
    # Create an assignment message
    assignment_message = InquiryMessage(
        inquiry_id=inquiry_id,
        sender_id=current_user.id,
        content=f"This inquiry has been assigned to {staff.get_full_name()}.",
        is_system_message=True
    )
    
    # Update inquiry status
    if inquiry.status == 'pending':
        inquiry.status = 'in_progress'
    
    # Log the assignment
    log = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action=f"Assigned inquiry #{inquiry_id} to {staff.get_full_name()}",
        target_type='inquiry',
        inquiry_id=inquiry_id,
        office_id=office_id,
        details=f"Inquiry: {inquiry.subject}"
    )
    
    db.session.add(assignment_message)
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Inquiry assigned to {staff.get_full_name()}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@office_bp.route('/api/staff-status-update', methods=['POST'])
@login_required
def staff_status_update():
    """API endpoint for staff to update their own status"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    status = request.json.get('status')
    custom_message = request.json.get('custom_message', '')
    
    valid_statuses = ['online', 'away', 'busy', 'offline']
    if status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    # Update user status
    current_user.is_online = status in ['online', 'away', 'busy']
    current_user.last_activity = datetime.utcnow()
    
    # Log the status change
    log = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action=f"Updated status to {status}",
        target_type='user',
        office_id=current_user.office_admin.office_id,
        details=custom_message if custom_message else None
    )
    
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Status updated to {status}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@office_bp.route('/api/post-team-announcement', methods=['POST'])
@login_required
def post_team_announcement():
    """API endpoint to post a team announcement"""
    if current_user.role != 'office_admin':
        return jsonify({'error': 'Not authorized'}), 403
    
    title = request.json.get('title', '').strip()
    content = request.json.get('content', '').strip()
    priority = request.json.get('priority', 'normal')
    audience = request.json.get('audience', 'office')
    
    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400
    
    valid_priorities = ['normal', 'important', 'urgent']
    valid_audiences = ['office', 'public']
    
    if priority not in valid_priorities:
        priority = 'normal'
    
    if audience not in valid_audiences:
        audience = 'office'
    
    office_id = current_user.office_admin.office_id
    
    # Create the announcement
    announcement = Announcement(
        title=title,
        content=content,
        author_id=current_user.id,
        target_office_id=office_id if audience == 'office' else None,
        is_public=audience == 'public',
        priority=priority,
        created_at=datetime.utcnow()
    )
    
    db.session.add(announcement)
    
    # Create notifications for relevant users
    if audience == 'office':
        # Notify all staff in the office
        office_staff = User.query.join(OfficeAdmin).filter(
            OfficeAdmin.office_id == office_id,
            User.id != current_user.id  # Don't notify the author
        ).all()
        
        for staff in office_staff:
            notification = Notification(
                user_id=staff.id,
                title=f"New Team Announcement: {title}",
                message=f"A new announcement has been posted by {current_user.get_full_name()}",
                notification_type='announcement',
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
    
    # Log the action
    log = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action=f"Posted {audience} announcement: {title}",
        target_type='announcement',
        office_id=office_id,
        details=f"Priority: {priority}"
    )
    
    db.session.add(log)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Announcement posted successfully to {audience} audience'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500