from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import time 
from sqlalchemy import func, case, desc, or_, and_
from app.office import office_bp
from app.utils import role_required
from app.office.routes.office_dashboard import get_office_context


@office_bp.route('/office-activity-logs')
@login_required
@role_required(['office_admin'])
def office_activity_logs():
    """View activity logs for the office"""
    office_id = current_user.office_admin.office_id
    
    # Get filter parameters
    action_filter = request.args.get('action', 'all')
    date_range = request.args.get('date_range', '7d')
    actor_type = request.args.get('actor_type', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    # Calculate date range
    now = datetime.utcnow()
    if date_range == '1d':
        start_date = now - timedelta(days=1)
    elif date_range == '7d':
        start_date = now - timedelta(days=7)
    elif date_range == '30d':
        start_date = now - timedelta(days=30)
    elif date_range == '90d':
        start_date = now - timedelta(days=90)
    else:
        start_date = now - timedelta(days=7)  # Default to 7 days
    
    # Base query for audit logs related to this office
    audit_query = AuditLog.query.filter(
        and_(
            AuditLog.office_id == office_id,
            AuditLog.timestamp >= start_date
        )
    )
    
    # Base query for office login logs
    login_query = OfficeLoginLog.query.join(OfficeAdmin).filter(
        and_(
            OfficeAdmin.office_id == office_id,
            OfficeLoginLog.login_time >= start_date
        )
    )
    
    # Apply action filter to audit logs
    if action_filter != 'all':
        audit_query = audit_query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    
    # Apply actor type filter
    if actor_type != 'all':
        audit_query = audit_query.filter(AuditLog.actor_role == actor_type)
        if actor_type == 'office_admin':
            # Only include login logs for office admin filter
            pass
        else:
            # For other actor types, exclude login logs
            login_query = login_query.filter(False)  # No results
    
    # Get audit logs
    audit_logs = audit_query.order_by(desc(AuditLog.timestamp)).limit(per_page).offset((page - 1) * per_page).all()
    
    # Get login logs (convert to a format similar to audit logs for unified display)
    login_logs = login_query.order_by(desc(OfficeLoginLog.login_time)).limit(per_page).offset((page - 1) * per_page).all()
    
    # Combine and sort all logs
    combined_logs = []
    
    # Add audit logs
    for log in audit_logs:
        combined_logs.append({
            'type': 'audit',
            'id': log.id,
            'timestamp': log.timestamp,
            'actor_name': f"{log.actor.first_name} {log.actor.last_name}" if log.actor else "System",
            'actor_role': log.actor_role or 'system',
            'action': log.action,
            'target_type': log.target_type,
            'status': 'success' if log.is_success else 'failed',
            'failure_reason': log.failure_reason,
            'ip_address': log.ip_address,
            'inquiry_id': log.inquiry_id,
            'details': {
                'status_snapshot': log.status_snapshot,
                'user_agent': log.user_agent
            }
        })
    
    # Add login logs
    for log in login_logs:
        duration_text = ""
        if log.session_duration:
            hours = log.session_duration // 3600
            minutes = (log.session_duration % 3600) // 60
            if hours > 0:
                duration_text = f"{hours}h {minutes}m"
            else:
                duration_text = f"{minutes}m"
        
        combined_logs.append({
            'type': 'login',
            'id': log.id,
            'timestamp': log.login_time,
            'actor_name': f"{log.office_admin.user.first_name} {log.office_admin.user.last_name}",
            'actor_role': 'office_admin',
            'action': 'Login' if log.is_success else 'Failed Login',
            'target_type': 'authentication',
            'status': 'success' if log.is_success else 'failed',
            'failure_reason': log.failure_reason,
            'ip_address': log.ip_address,
            'details': {
                'logout_time': log.logout_time,
                'session_duration': duration_text,
                'user_agent': log.user_agent
            }
        })
    
    # Sort combined logs by timestamp (newest first)
    combined_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Paginate combined logs
    total_logs = len(combined_logs)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_logs = combined_logs[start_idx:end_idx]
    
    # Get unique actions for filter dropdown
    unique_actions = db.session.query(AuditLog.action).filter(
        AuditLog.office_id == office_id
    ).distinct().all()
    actions = [action[0] for action in unique_actions if action[0]]
    
    # Get activity statistics
    stats = {
        'total_activities': total_logs,
        'successful_actions': len([log for log in combined_logs if log['status'] == 'success']),
        'failed_actions': len([log for log in combined_logs if log['status'] == 'failed']),
        'unique_users': len(set([log['actor_name'] for log in combined_logs if log['actor_name'] != 'System']))
    }
    
    # Get pagination info
    has_prev = page > 1
    has_next = end_idx < total_logs
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    
    pagination = {
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': prev_num,
        'next_num': next_num,
        'page': page,
        'per_page': per_page,
        'total': total_logs,
        'pages': (total_logs + per_page - 1) // per_page
    }
    
    # Get context data for sidebar
    context = get_office_context()
    
    return render_template('office/office_activity_logs.html',
                         logs=paginated_logs,
                         actions=actions,
                         stats=stats,
                         pagination=pagination,
                         current_action_filter=action_filter,
                         current_date_range=date_range,
                         current_actor_type=actor_type,
                         **context)


@office_bp.route('/office-activity-logs/export')
@login_required
@role_required(['office_admin'])
def export_activity_logs():
    """Export activity logs as CSV"""
    import csv
    import io
    
    office_id = current_user.office_admin.office_id
    
    # Get filter parameters
    action_filter = request.args.get('action', 'all')
    date_range = request.args.get('date_range', '30d')
    actor_type = request.args.get('actor_type', 'all')
    
    # Calculate date range
    now = datetime.utcnow()
    if date_range == '1d':
        start_date = now - timedelta(days=1)
    elif date_range == '7d':
        start_date = now - timedelta(days=7)
    elif date_range == '30d':
        start_date = now - timedelta(days=30)
    elif date_range == '90d':
        start_date = now - timedelta(days=90)
    else:
        start_date = now - timedelta(days=30)
    
    # Get all logs for export (no pagination)
    audit_query = AuditLog.query.filter(
        and_(
            AuditLog.office_id == office_id,
            AuditLog.timestamp >= start_date
        )
    )
    
    login_query = OfficeLoginLog.query.join(OfficeAdmin).filter(
        and_(
            OfficeAdmin.office_id == office_id,
            OfficeLoginLog.login_time >= start_date
        )
    )
    
    # Apply filters
    if action_filter != 'all':
        audit_query = audit_query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    
    if actor_type != 'all':
        audit_query = audit_query.filter(AuditLog.actor_role == actor_type)
        if actor_type != 'office_admin':
            login_query = login_query.filter(False)
    
    # Get logs
    audit_logs = audit_query.order_by(desc(AuditLog.timestamp)).all()
    login_logs = login_query.order_by(desc(OfficeLoginLog.login_time)).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Timestamp', 'Actor', 'Role', 'Action', 'Target Type', 
        'Status', 'IP Address', 'Details', 'Failure Reason'
    ])
    
    # Combine logs for export
    all_logs = []
    
    for log in audit_logs:
        all_logs.append({
            'timestamp': log.timestamp,
            'actor_name': f"{log.actor.first_name} {log.actor.last_name}" if log.actor else "System",
            'actor_role': log.actor_role or 'system',
            'action': log.action,
            'target_type': log.target_type,
            'status': 'Success' if log.is_success else 'Failed',
            'ip_address': log.ip_address or '',
            'details': log.status_snapshot or '',
            'failure_reason': log.failure_reason or ''
        })
    
    for log in login_logs:
        duration = ""
        if log.session_duration:
            hours = log.session_duration // 3600
            minutes = (log.session_duration % 3600) // 60
            duration = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        all_logs.append({
            'timestamp': log.login_time,
            'actor_name': f"{log.office_admin.user.first_name} {log.office_admin.user.last_name}",
            'actor_role': 'office_admin',
            'action': 'Login' if log.is_success else 'Failed Login',
            'target_type': 'authentication',
            'status': 'Success' if log.is_success else 'Failed',
            'ip_address': log.ip_address or '',
            'details': f"Session: {duration}" if duration else '',
            'failure_reason': log.failure_reason or ''
        })
    
    # Sort by timestamp
    all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Write data
    for log in all_logs:
        writer.writerow([
            log['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            log['actor_name'],
            log['actor_role'].replace('_', ' ').title(),
            log['action'],
            log['target_type'].replace('_', ' ').title() if log['target_type'] else '',
            log['status'],
            log['ip_address'],
            log['details'],
            log['failure_reason']
        ])
    
    output.seek(0)
    
    # Create response
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=office_activity_logs_{start_date.strftime("%Y%m%d")}_{now.strftime("%Y%m%d")}.csv'
    
    return response