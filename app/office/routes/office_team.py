from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog
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