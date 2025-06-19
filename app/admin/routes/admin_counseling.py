from app.models import (
    CounselingSession, User, Office, db, Student,
    SuperAdminActivityLog
)
from flask import Blueprint, render_template, jsonify, request, Response, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
from sqlalchemy.orm import aliased
import csv
import io
from app.admin import admin_bp

@admin_bp.route('/counseling-sessions')
@login_required
def admin_counseling():
    """Admin dashboard for counseling sessions management"""
    if current_user.role != 'super_admin':
        return redirect(url_for('main.index'))
    
    # Get all offices for the filter dropdown
    offices = Office.query.all()
    
    # Calculate statistics for dashboard cards
    total_sessions = CounselingSession.query.count()
    
    # Status counts
    pending_sessions = CounselingSession.query.filter_by(status='pending').count()
    completed_sessions = CounselingSession.query.filter_by(status='completed').count()
    cancelled_sessions = CounselingSession.query.filter_by(status='cancelled').count()
    no_show_sessions = CounselingSession.query.filter_by(status='no-show').count()
    
    # Calculate percentages
    pending_sessions_percent = round((pending_sessions / total_sessions * 100) if total_sessions > 0 else 0)
    completed_sessions_percent = round((completed_sessions / total_sessions * 100) if total_sessions > 0 else 0)
    cancelled_sessions_percent = round((cancelled_sessions / total_sessions * 100) if total_sessions > 0 else 0)
    
    # Calculate trend
    # Compare with previous month
    today = datetime.utcnow()
    first_day_current_month = datetime(today.year, today.month, 1)
    first_day_previous_month = first_day_current_month - timedelta(days=first_day_current_month.day)
    
    current_month_sessions = CounselingSession.query.filter(
        CounselingSession.scheduled_at >= first_day_current_month
    ).count()
    
    prev_month_sessions = CounselingSession.query.filter(
        CounselingSession.scheduled_at >= first_day_previous_month,
        CounselingSession.scheduled_at < first_day_current_month
    ).count()
    
    # Calculate percentage change
    if prev_month_sessions > 0:
        session_trend = round(((current_month_sessions - prev_month_sessions) / prev_month_sessions) * 100)
    else:
        session_trend = 100 if current_month_sessions > 0 else 0
    
    # Get counseling sessions with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Create aliases for the User table to handle multiple joins
    StudentUser = aliased(User)
    CounselorUser = aliased(User)
    
    counseling_sessions = CounselingSession.query\
        .join(Student, CounselingSession.student_id == Student.id)\
        .join(StudentUser, Student.user_id == StudentUser.id)\
        .join(Office, CounselingSession.office_id == Office.id)\
        .join(CounselorUser, CounselingSession.counselor_id == CounselorUser.id)\
        .order_by(CounselingSession.scheduled_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Log admin activity
    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action="Viewed counseling sessions",
        target_type="system",
        details="Accessed counseling sessions management dashboard",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'admin/admin_counseling.html',
        total_sessions=total_sessions,
        pending_sessions=pending_sessions,
        completed_sessions=completed_sessions,
        cancelled_sessions=cancelled_sessions,
        pending_sessions_percent=pending_sessions_percent,
        completed_sessions_percent=completed_sessions_percent,
        cancelled_sessions_percent=cancelled_sessions_percent,
        session_trend=session_trend,
        offices=offices,
        counseling_sessions=counseling_sessions.items
    )

@admin_bp.route('/counseling-sessions/filter')
@login_required
def filter_counseling_sessions():
    """Filter counseling sessions based on search criteria"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get filter parameters
    search_term = request.args.get('search', '')
    office_id = request.args.get('office_id', '')
    status = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Create aliases for the User table to handle multiple joins
    StudentUser = aliased(User)
    CounselorUser = aliased(User)
    
    # Build the query
    query = CounselingSession.query\
        .join(Student, CounselingSession.student_id == Student.id)\
        .join(StudentUser, Student.user_id == StudentUser.id)\
        .join(Office, CounselingSession.office_id == Office.id)\
        .join(CounselorUser, CounselingSession.counselor_id == CounselorUser.id)
    
    # Apply filters
    if search_term:
        search_term = f"%{search_term}%"
        query = query.filter(
            or_(
                StudentUser.first_name.ilike(search_term),
                StudentUser.last_name.ilike(search_term),
                CounselorUser.first_name.ilike(search_term),
                CounselorUser.last_name.ilike(search_term),
                Office.name.ilike(search_term)
            )
        )
    
    if office_id:
        query = query.filter(Office.id == office_id)
    
    if status:
        query = query.filter(CounselingSession.status == status)
    
    if date_filter:
        date_obj = datetime.strptime(date_filter, '%Y-%m-%d')
        next_day = date_obj + timedelta(days=1)
        query = query.filter(
            CounselingSession.scheduled_at >= date_obj,
            CounselingSession.scheduled_at < next_day
        )
    
    # Order by scheduled date (newest first)
    query = query.order_by(CounselingSession.scheduled_at.desc())
    
    # Paginate results
    paginated_sessions = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Prepare response
    sessions_data = []
    for session in paginated_sessions.items:
        student = User.query.join(Student).filter(Student.id == session.student_id).first()
        counselor = User.query.filter_by(id=session.counselor_id).first()
        office = Office.query.filter_by(id=session.office_id).first()
        
        sessions_data.append({
            'id': session.id,
            'student': student.get_full_name() if student else 'Unknown',
            'office': office.name if office else 'Unknown',
            'counselor': counselor.get_full_name() if counselor else 'Unknown',
            'scheduled_at': session.scheduled_at.strftime('%Y-%m-%d %H:%M'),
            'status': session.status
        })
    
    return jsonify(sessions_data)

@admin_bp.route('/counseling-sessions/<int:session_id>')
@login_required
def get_session_details(session_id):
    """Get details for a specific counseling session"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    session = CounselingSession.query.get_or_404(session_id)
    
    # Get related data
    student = User.query.join(Student).filter(Student.id == session.student_id).first()
    counselor = User.query.filter_by(id=session.counselor_id).first()
    office = Office.query.filter_by(id=session.office_id).first()
    
    # Log the view action
    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action="Viewed session details",
        target_type="counseling_session",
        details=f"Viewed details for counseling session #{session_id}",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    # Prepare the session details
    session_data = {
        'id': session.id,
        'student': student.get_full_name() if student else 'Unknown',
        'office': office.name if office else 'Unknown',
        'counselor': counselor.get_full_name() if counselor else 'Unknown',
        'scheduled_at': session.scheduled_at.strftime('%Y-%m-%d %H:%M'),
        'status': session.status,
        'notes': session.notes or 'No notes available'
    }
    
    return jsonify(session_data)

@admin_bp.route('/counseling-sessions/export')
@login_required
def export_counseling_csv():
    """Export counseling sessions to CSV"""
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get filter parameters for export
    search_term = request.args.get('search', '')
    office_id = request.args.get('office_id', '')
    status = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    
    # Create aliases for the User table to handle multiple joins
    StudentUser = aliased(User)
    CounselorUser = aliased(User)
    
    # Build the query
    query = CounselingSession.query\
        .join(Student, CounselingSession.student_id == Student.id)\
        .join(StudentUser, Student.user_id == StudentUser.id)\
        .join(Office, CounselingSession.office_id == Office.id)\
        .join(CounselorUser, CounselingSession.counselor_id == CounselorUser.id)
    
    # Apply filters
    if search_term:
        search_term = f"%{search_term}%"
        query = query.filter(
            or_(
                StudentUser.first_name.ilike(search_term),
                StudentUser.last_name.ilike(search_term),
                CounselorUser.first_name.ilike(search_term),
                CounselorUser.last_name.ilike(search_term),
                Office.name.ilike(search_term)
            )
        )
    
    if office_id:
        query = query.filter(Office.id == office_id)
    
    if status:
        query = query.filter(CounselingSession.status == status)
    
    if date_filter:
        date_obj = datetime.strptime(date_filter, '%Y-%m-%d')
        next_day = date_obj + timedelta(days=1)
        query = query.filter(
            CounselingSession.scheduled_at >= date_obj,
            CounselingSession.scheduled_at < next_day
        )
    
    # Order by scheduled date
    sessions = query.order_by(CounselingSession.scheduled_at.desc()).all()
    
    # Create a CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Student', 'Office', 'Counselor', 'Scheduled Date', 'Status', 'Notes'])
    
    # Write data
    for session in sessions:
        student = User.query.join(Student).filter(Student.id == session.student_id).first()
        counselor = User.query.filter_by(id=session.counselor_id).first()
        office = Office.query.filter_by(id=session.office_id).first()
        
        writer.writerow([
            session.id,
            student.get_full_name() if student else 'Unknown',
            office.name if office else 'Unknown',
            counselor.get_full_name() if counselor else 'Unknown',
            session.scheduled_at.strftime('%Y-%m-%d %H:%M'),
            session.status,
            session.notes or ''
        ])
    
    # Log the export action
    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action="Exported counseling sessions",
        target_type="counseling_session",
        details="Exported counseling sessions to CSV",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    # Prepare response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=counseling_sessions.csv"}
    )