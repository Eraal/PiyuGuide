from flask_socketio import emit, join_room, leave_room, disconnect
from flask_login import current_user
from app.extensions import socketio
from app.models import Inquiry, CounselingSession, AuditLog, Office, User
from datetime import datetime, timedelta
from sqlalchemy import func
import json

# Dashboard namespace for real-time updates
@socketio.on('connect', namespace='/dashboard')
def dashboard_connect():
    """Handle client connection to dashboard namespace"""
    if not current_user.is_authenticated or current_user.role not in ['super_admin', 'office_admin']:
        print("Unauthorized dashboard connection attempt")
        disconnect()
        return False
    
    print(f"Dashboard connected: {current_user.email}")
    join_room('dashboard_room', namespace='/dashboard')
    
    # Send initial dashboard data
    emit('dashboard_connected', {
        'status': 'connected',
        'user': {
            'id': current_user.id,
            'name': f"{current_user.first_name} {current_user.last_name}",
            'role': current_user.role
        }
    }, namespace='/dashboard')

@socketio.on('disconnect', namespace='/dashboard')
def dashboard_disconnect():
    """Handle client disconnection from dashboard namespace"""
    if current_user.is_authenticated:
        print(f"Dashboard disconnected: {current_user.email}")
        leave_room('dashboard_room', namespace='/dashboard')

@socketio.on('request_dashboard_update', namespace='/dashboard')
def handle_dashboard_update_request():
    """Handle request for fresh dashboard data"""
    if not current_user.is_authenticated or current_user.role not in ['super_admin', 'office_admin']:
        return
    
    # Get fresh dashboard statistics
    dashboard_data = get_dashboard_stats()
    emit('dashboard_update', dashboard_data, namespace='/dashboard')

def get_dashboard_stats():
    """Get current dashboard statistics"""
    total_students = User.query.filter_by(role='student').count()
    total_office_admins = User.query.filter_by(role='office_admin').count()
    total_inquiries = Inquiry.query.count()
    pending_inquiries = Inquiry.query.filter_by(status='pending').count()
    resolved_inquiries = Inquiry.query.filter_by(status='resolved').count()
    
    # Office data
    office_data = []
    offices = Office.query.all()
    for office in offices:
        inquiry_count = Inquiry.query.filter_by(office_id=office.id).count()
        office_data.append({
            "id": office.id,
            "name": office.name,
            "count": inquiry_count
        })
    
    # Get chart data
    today = datetime.utcnow()
    weekly_data = get_weekly_chart_data(today)
    monthly_data = get_monthly_chart_data(today)
    
    return {
        'total_students': total_students,
        'total_office_admins': total_office_admins,
        'total_inquiries': total_inquiries,
        'pending_inquiries': pending_inquiries,
        'resolved_inquiries': resolved_inquiries,
        'offices': office_data,
        'weekly_chart_data': weekly_data,
        'monthly_chart_data': monthly_data,
        'timestamp': datetime.utcnow().isoformat()
    }

def get_weekly_chart_data(today):
    """Get weekly chart data for the last 7 days"""
    weekly_new_inquiries = [0] * 7
    weekly_resolved = [0] * 7
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_of_week = day.weekday()
        chart_index = (day_of_week + 1) % 7  # Adjust for Sunday=0
        
        new_count = Inquiry.query.filter(func.date(Inquiry.created_at) == day.date()).count()
        resolved_count = Inquiry.query.filter(
            func.date(Inquiry.created_at) == day.date(),
            Inquiry.status == 'resolved'
        ).count()
        
        weekly_new_inquiries[chart_index] = new_count
        weekly_resolved[chart_index] = resolved_count
    
    return {
        'labels': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        'new_inquiries': weekly_new_inquiries,
        'resolved': weekly_resolved
    }

def get_monthly_chart_data(today):
    """Get monthly chart data for the last 12 months"""
    monthly_new_inquiries = [0] * 12
    monthly_resolved = [0] * 12
    current_month = today.month - 1  # 0-based index
    
    for i in range(12):
        month_index = (current_month - 11 + i) % 12
        year_offset = 0 if month_index <= current_month else -1
        query_year = today.year + year_offset
        db_month = month_index + 1
        
        monthly_new_inquiries[i] = Inquiry.query.filter(
            func.extract('year', Inquiry.created_at) == query_year,
            func.extract('month', Inquiry.created_at) == db_month
        ).count()
        
        monthly_resolved[i] = Inquiry.query.filter(
            func.extract('year', Inquiry.created_at) == query_year,
            func.extract('month', Inquiry.created_at) == db_month,
            Inquiry.status == 'resolved'
        ).count()
    
    return {
        'labels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
        'new_inquiries': monthly_new_inquiries,
        'resolved': monthly_resolved
    }

# Functions to broadcast real-time updates
def broadcast_new_inquiry(inquiry_data):
    """Broadcast new inquiry to dashboard"""
    socketio.emit('new_inquiry', {
        'inquiry_id': inquiry_data.get('id'),
        'student_name': inquiry_data.get('student_name'),
        'subject': inquiry_data.get('subject'),
        'office_name': inquiry_data.get('office_name'),
        'timestamp': datetime.utcnow().isoformat()
    }, room='dashboard_room', namespace='/dashboard')

def broadcast_resolved_inquiry(inquiry_data):
    """Broadcast resolved inquiry to dashboard"""
    socketio.emit('resolved_inquiry', {
        'inquiry_id': inquiry_data.get('id'),
        'resolver': inquiry_data.get('resolver'),
        'timestamp': datetime.utcnow().isoformat()
    }, room='dashboard_room', namespace='/dashboard')

def broadcast_new_session(session_data):
    """Broadcast new counseling session to dashboard"""
    socketio.emit('new_session', {
        'session_id': session_data.get('id'),
        'student': session_data.get('student'),
        'office': session_data.get('office'),
        'scheduled_at': session_data.get('scheduled_at'),
        'status': session_data.get('status'),
        'creator': session_data.get('creator'),
        'timestamp': datetime.utcnow().isoformat()
    }, room='dashboard_room', namespace='/dashboard')

def broadcast_system_log(log_data):
    """Broadcast system log to dashboard"""
    socketio.emit('system_log', {
        'action': log_data.get('action'),
        'actor': log_data.get('actor'),
        'is_success': log_data.get('is_success', True),
        'timestamp': datetime.utcnow().isoformat()
    }, room='dashboard_room', namespace='/dashboard')

def broadcast_dashboard_update():
    """Broadcast full dashboard update to all connected clients"""
    dashboard_data = get_dashboard_stats()
    socketio.emit('dashboard_update', dashboard_data, room='dashboard_room', namespace='/dashboard')
