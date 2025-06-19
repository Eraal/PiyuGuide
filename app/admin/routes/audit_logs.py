from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp

################################# AUDIT LOGS ###############################################

@admin_bp.route('/audit-logs')
@login_required
def audit_logs():
    if current_user.role != 'super_admin':
        flash('Unauthorized access', 'error')
        return redirect(url_for('main.index'))
        
    filter_type = request.args.get('filter_type', 'all')
    search_query = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    role = request.args.get('role', '')
    action = request.args.get('action', '')
    status = request.args.get('status', '')
    
    # Create a dictionary of filter params to pass to view functions
    filter_params = {
        'search': search_query,
        'date_from': date_from, 
        'date_to': date_to,
        'role': role,
        'action': action,
        'status': status
    }
    
    if filter_type == 'student':
        return handle_student_logs(filter_params)
    elif filter_type == 'office':
        return handle_office_logs(filter_params)
    elif filter_type == 'superadmin':
        return handle_superadmin_logs(filter_params)
    else:  # 'all' or any other value
        return handle_all_logs(filter_params)


def handle_student_logs(filter_params):
    """Handle student activity logs filtering and display"""
    student_logs_query = db.session.query(
        StudentActivityLog, Student, User
    ).join(
        Student, StudentActivityLog.student_id == Student.id
    ).join(
        User, Student.user_id == User.id
    ).order_by(StudentActivityLog.timestamp.desc())
    
    if filter_params['search']:
        student_logs_query = student_logs_query.filter(
            or_(
                User.first_name.ilike(f"%{filter_params['search']}%"),
                User.last_name.ilike(f"%{filter_params['search']}%"),
                User.email.ilike(f"%{filter_params['search']}%"),
                StudentActivityLog.action.ilike(f"%{filter_params['search']}%")
            )
        )
    
    if filter_params['date_from']:
        student_logs_query = student_logs_query.filter(StudentActivityLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
    
    if filter_params['date_to']:
        student_logs_query = student_logs_query.filter(StudentActivityLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    students_query = db.session.query(
        User,
        Student,
        func.count(Inquiry.id).label('total_inquiries'),
        func.sum(case((Inquiry.status == 'pending', 1), else_=0)).label('active_inquiries'),
        func.count(CounselingSession.id).label('counseling_sessions')
    ).join(
        Student, User.id == Student.user_id
    ).outerjoin(
        Inquiry, Student.id == Inquiry.student_id
    ).outerjoin(
        CounselingSession, Student.id == CounselingSession.student_id
    ).group_by(
        User.id, Student.id
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    paginated_logs = student_logs_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format student logs for display
    formatted_logs = []
    for log, student, user in paginated_logs.items:
        formatted_logs.append({
            'id': log.id,
            'student_name': f"{user.first_name} {user.last_name}",
            'student_email': user.email,
            'action': log.action,
            'related_type': log.related_type,
            'is_success': log.is_success,
            'timestamp': log.timestamp,
            'ip_address': log.ip_address
        })
    
    return render_template('admin/audit_logs.html', 
                          students=students_query.all(),
                          student_logs=formatted_logs,
                          pagination=paginated_logs,
                          filter_type='student',
                          search_query=filter_params['search'],
                          view_type='student')


def handle_office_logs(filter_params):
    """Handle office login logs filtering and display"""
    office_logs_query = db.session.query(
        OfficeLoginLog, OfficeAdmin, User, Office
    ).join(
        OfficeAdmin, OfficeLoginLog.office_admin_id == OfficeAdmin.id
    ).join(
        User, OfficeAdmin.user_id == User.id
    ).join(
        Office, OfficeAdmin.office_id == Office.id
    ).order_by(OfficeLoginLog.login_time.desc())
    
    if filter_params['search']:
        office_logs_query = office_logs_query.filter(
            or_(
                User.first_name.ilike(f"%{filter_params['search']}%"),
                User.last_name.ilike(f"%{filter_params['search']}%"),
                User.email.ilike(f"%{filter_params['search']}%"),
                Office.name.ilike(f"%{filter_params['search']}%")
            )
        )
    
    if filter_params['date_from']:
        office_logs_query = office_logs_query.filter(OfficeLoginLog.login_time >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
    
    if filter_params['date_to']:
        office_logs_query = office_logs_query.filter(OfficeLoginLog.login_time <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    offices_query = db.session.query(
        Office,
        func.count(Inquiry.id).label('total_inquiries'),
        func.sum(case((Inquiry.status == 'pending', 1), else_=0)).label('pending_inquiries'),
        func.sum(case((Inquiry.status == 'resolved', 1), else_=0)).label('resolved_inquiries'),
        func.count(CounselingSession.id).label('counseling_sessions')
    ).outerjoin(
        Inquiry, Office.id == Inquiry.office_id
    ).outerjoin(
        CounselingSession, Office.id == CounselingSession.office_id
    ).group_by(
        Office.id
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    paginated_logs = office_logs_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format office logs for display
    formatted_logs = []
    for log, office_admin, user, office in paginated_logs.items:
        formatted_logs.append({
            'id': log.id,
            'admin_name': f"{user.first_name} {user.last_name}",
            'admin_email': user.email,
            'office_name': office.name,
            'login_time': log.login_time,
            'logout_time': log.logout_time,
            'session_duration': log.session_duration,
            'is_success': log.is_success,
            'ip_address': log.ip_address
        })
    
    return render_template('admin/audit_logs.html', 
                          offices=offices_query.all(),
                          office_logs=formatted_logs,
                          pagination=paginated_logs,
                          filter_type='office',
                          search_query=filter_params['search'],
                          view_type='office')

def handle_superadmin_logs(filter_params):
    """Handle super admin activity logs filtering and display"""
    superadmin_logs_query = db.session.query(
        SuperAdminActivityLog, 
        User.first_name.label('admin_first_name'),
        User.last_name.label('admin_last_name'),
        User.email.label('admin_email')
    ).outerjoin(
        User, SuperAdminActivityLog.super_admin_id == User.id
    ).order_by(SuperAdminActivityLog.timestamp.desc())
    
    if filter_params['search']:
        superadmin_logs_query = superadmin_logs_query.filter(
            or_(
                User.first_name.ilike(f"%{filter_params['search']}%"),
                User.last_name.ilike(f"%{filter_params['search']}%"),
                User.email.ilike(f"%{filter_params['search']}%"),
                SuperAdminActivityLog.action.ilike(f"%{filter_params['search']}%"),
                SuperAdminActivityLog.target_type.ilike(f"%{filter_params['search']}%")
            )
        )
    
    if filter_params['date_from']:
        superadmin_logs_query = superadmin_logs_query.filter(SuperAdminActivityLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
    
    if filter_params['date_to']:
        superadmin_logs_query = superadmin_logs_query.filter(SuperAdminActivityLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    super_admins_query = db.session.query(
        User,
        func.count(SuperAdminActivityLog.id).label('total_actions')
    ).outerjoin(
        SuperAdminActivityLog, User.id == SuperAdminActivityLog.super_admin_id
    ).filter(
        User.role == 'super_admin'
    ).group_by(
        User.id
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    paginated_logs = superadmin_logs_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format super admin logs for display
    formatted_logs = []
    for log_data in paginated_logs.items:
        log = log_data[0]  # Extract the actual log object
        formatted_logs.append({
            'id': log.id,
            'admin_name': f"{log_data.admin_first_name} {log_data.admin_last_name}" if log_data.admin_first_name else "Unknown",
            'admin_email': log_data.admin_email,
            'action': log.action,
            'target_type': log.target_type,
            'details': log.details,
            'is_success': log.is_success,
            'timestamp': log.timestamp,
            'ip_address': log.ip_address
        })
    
    return render_template('admin/audit_logs.html', 
                          super_admins=super_admins_query.all(),
                          superadmin_logs=formatted_logs,
                          pagination=paginated_logs,
                          filter_type='superadmin',
                          search_query=filter_params['search'],
                          view_type='superadmin')


def handle_all_logs(filter_params):
    """Handle all audit logs filtering and display"""
    audit_logs_query = db.session.query(
        AuditLog,
        User.first_name.label('user_first_name'),
        User.last_name.label('user_last_name'),
        User.email.label('user_email'),
        User.role.label('user_role')
    ).outerjoin(
        User, AuditLog.actor_id == User.id
    ).order_by(AuditLog.timestamp.desc())
    
    if filter_params['search']:
        audit_logs_query = audit_logs_query.filter(
            or_(
                User.first_name.ilike(f"%{filter_params['search']}%"),
                User.last_name.ilike(f"%{filter_params['search']}%"),
                User.email.ilike(f"%{filter_params['search']}%"),
                AuditLog.action.ilike(f"%{filter_params['search']}%"),
                AuditLog.target_type.ilike(f"%{filter_params['search']}%")
            )
        )
    
    if filter_params['date_from']:
        audit_logs_query = audit_logs_query.filter(AuditLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
    
    if filter_params['date_to']:
        audit_logs_query = audit_logs_query.filter(AuditLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    paginated_logs = audit_logs_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format audit logs for display
    formatted_logs = []
    for log_data in paginated_logs.items:
        log = log_data[0]  # Extract the actual log object
        formatted_logs.append({
            'id': log.id,
            'action': log.action,
            'timestamp': log.timestamp,
            'is_success': log.is_success,
            'ip_address': log.ip_address,
            'user_name': f"{log_data.user_first_name} {log_data.user_last_name}" if log_data.user_first_name else "Unknown",
            'user_email': log_data.user_email,
            'user_role': log_data.user_role,
            'related_type': log.target_type
        })

    return render_template('admin/audit_logs.html', 
                          audit_logs=formatted_logs,
                          pagination=paginated_logs,
                          filter_type='all',
                          search_query=filter_params['search'],
                          view_type='all')


@admin_bp.route('/export-logs', methods=['GET'])
@login_required
def export_logs():
    """Export logs in various formats."""
    if current_user.role != 'super_admin':
        flash('Unauthorized access', 'error')
        return redirect(url_for('main.index'))
        
    export_format = request.args.get('format', 'csv')
    log_type = request.args.get('type', 'all')
    
    # Get all filter parameters to pass to the log retrieval function
    filter_params = {
        'search': request.args.get('search', ''),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', ''),
        'role': request.args.get('role', ''),
        'status': request.args.get('status', ''),
        'action': request.args.get('action', '')
    }
    
    logs = get_logs_based_on_type_and_filters(log_type, filter_params)
    
    if export_format == 'csv':
        return export_logs_csv(logs, log_type)
    elif export_format == 'excel':
        return export_logs_excel(logs, log_type)
    elif export_format == 'pdf':
        return export_logs_pdf(logs, log_type)
    else:
        flash('Unsupported export format', 'error')
        return redirect(url_for('admin.audit_logs', filter_type=log_type))


def get_logs_based_on_type_and_filters(log_type, filter_params):
    """Get logs based on type and applied filters."""
    if log_type == 'student':
        query = db.session.query(
            StudentActivityLog, Student, User
        ).join(
            Student, StudentActivityLog.student_id == Student.id
        ).join(
            User, Student.user_id == User.id
        )
        
        if filter_params['search']:
            query = query.filter(
                or_(
                    User.first_name.ilike(f'%{filter_params["search"]}%'),
                    User.last_name.ilike(f'%{filter_params["search"]}%'),
                    User.email.ilike(f'%{filter_params["search"]}%'),
                    StudentActivityLog.action.ilike(f'%{filter_params["search"]}%')
                )
            )
            
        if filter_params['date_from']:
            query = query.filter(StudentActivityLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
        
        if filter_params['date_to']:
            query = query.filter(StudentActivityLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            
        return query.order_by(StudentActivityLog.timestamp.desc()).all()
        
    elif log_type == 'office':
        query = db.session.query(
            OfficeLoginLog, OfficeAdmin, User, Office
        ).join(
            OfficeAdmin, OfficeLoginLog.office_admin_id == OfficeAdmin.id
        ).join(
            User, OfficeAdmin.user_id == User.id
        ).join(
            Office, OfficeAdmin.office_id == Office.id
        )
        
        if filter_params['search']:
            query = query.filter(
                or_(
                    User.first_name.ilike(f'%{filter_params["search"]}%'),
                    User.last_name.ilike(f'%{filter_params["search"]}%'),
                    User.email.ilike(f'%{filter_params["search"]}%'),
                    Office.name.ilike(f'%{filter_params["search"]}%')
                )
            )
            
        if filter_params['date_from']:
            query = query.filter(OfficeLoginLog.login_time >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
        
        if filter_params['date_to']:
            query = query.filter(OfficeLoginLog.login_time <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            
        return query.order_by(OfficeLoginLog.login_time.desc()).all()
        
    elif log_type == 'superadmin':
        query = db.session.query(
            SuperAdminActivityLog, User
        ).outerjoin(
            User, SuperAdminActivityLog.super_admin_id == User.id
        )
        
        if filter_params['search']:
            query = query.filter(
                or_(
                    User.first_name.ilike(f'%{filter_params["search"]}%'),
                    User.last_name.ilike(f'%{filter_params["search"]}%'),
                    User.email.ilike(f'%{filter_params["search"]}%'),
                    SuperAdminActivityLog.action.ilike(f'%{filter_params["search"]}%'),
                    SuperAdminActivityLog.target_type.ilike(f'%{filter_params["search"]}%')
                )
            )
            
        if filter_params['date_from']:
            query = query.filter(SuperAdminActivityLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
        
        if filter_params['date_to']:
            query = query.filter(SuperAdminActivityLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            
        return query.order_by(SuperAdminActivityLog.timestamp.desc()).all()
        
    else:  # 'all' or any other value
        query = db.session.query(
            AuditLog, User
        ).outerjoin(
            User, AuditLog.actor_id == User.id
        )
        
        if filter_params['search']:
            query = query.filter(
                or_(
                    User.first_name.ilike(f'%{filter_params["search"]}%') if User else False,
                    User.last_name.ilike(f'%{filter_params["search"]}%') if User else False,
                    User.email.ilike(f'%{filter_params["search"]}%') if User else False,
                    AuditLog.action.ilike(f'%{filter_params["search"]}%'),
                    AuditLog.target_type.ilike(f'%{filter_params["search"]}%')
                )
            )
            
        if filter_params['date_from']:
            query = query.filter(AuditLog.timestamp >= datetime.strptime(filter_params['date_from'], '%Y-%m-%d'))
        
        if filter_params['date_to']:
            query = query.filter(AuditLog.timestamp <= datetime.strptime(filter_params['date_to'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
            
        return query.order_by(AuditLog.timestamp.desc()).all()


def export_logs_csv(logs, log_type):
    """Export logs as CSV file."""
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    if log_type == 'student':
        writer.writerow(['ID', 'Student Name', 'Email', 'Action', 'Related Type', 'Status', 'Timestamp', 'IP Address'])
        
        for log, student, user in logs:
            writer.writerow([
                log.id,
                f"{user.first_name} {user.last_name}",
                user.email,
                log.action,
                log.related_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    elif log_type == 'office':
        writer.writerow(['ID', 'Admin Name', 'Email', 'Office', 'Login Time', 'Logout Time', 'Duration (sec)', 'Status', 'IP Address'])
        
        for log, office_admin, user, office in logs:
            writer.writerow([
                log.id,
                f"{user.first_name} {user.last_name}",
                user.email,
                office.name,
                log.login_time.strftime('%Y-%m-%d %H:%M:%S'),
                log.logout_time.strftime('%Y-%m-%d %H:%M:%S') if log.logout_time else '',
                log.session_duration or '',
                'Success' if log.is_success else 'Failed',
                log.ip_address or ''
            ])
            
    elif log_type == 'superadmin':
        writer.writerow(['ID', 'Admin Name', 'Email', 'Action', 'Target Type', 'Details', 'Status', 'Timestamp', 'IP Address'])
        
        for log, user in logs:
            writer.writerow([
                log.id,
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.email if user else '',
                log.action,
                log.target_type or '',
                log.details or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    else:  # 'all' or any other value
        writer.writerow(['ID', 'User', 'Role', 'Action', 'Target Type', 'Status', 'Timestamp', 'IP Address'])
        
        for log, user in logs:
            writer.writerow([
                log.id,
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.role if user else '',
                log.action,
                log.target_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={log_type}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )


def export_logs_excel(logs, log_type):
    """Export logs as Excel file."""
    import openpyxl
    from io import BytesIO
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{log_type.capitalize()} Logs"
    
    if log_type == 'student':
        ws.append(['ID', 'Student Name', 'Email', 'Action', 'Related Type', 'Status', 'Timestamp', 'IP Address'])
        
        for log, student, user in logs:
            ws.append([
                log.id,
                f"{user.first_name} {user.last_name}",
                user.email,
                log.action,
                log.related_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    elif log_type == 'office':
        ws.append(['ID', 'Admin Name', 'Email', 'Office', 'Login Time', 'Logout Time', 'Duration (sec)', 'Status', 'IP Address'])
        
        for log, office_admin, user, office in logs:
            ws.append([
                log.id,
                f"{user.first_name} {user.last_name}",
                user.email,
                office.name,
                log.login_time.strftime('%Y-%m-%d %H:%M:%S'),
                log.logout_time.strftime('%Y-%m-%d %H:%M:%S') if log.logout_time else '',
                log.session_duration or '',
                'Success' if log.is_success else 'Failed',
                log.ip_address or ''
            ])
            
    elif log_type == 'superadmin':
        ws.append(['ID', 'Admin Name', 'Email', 'Action', 'Target Type', 'Details', 'Status', 'Timestamp', 'IP Address'])
        
        for log, user in logs:
            ws.append([
                log.id,
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.email if user else '',
                log.action,
                log.target_type or '',
                log.details or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    else:  # 'all' or any other value
        ws.append(['ID', 'User', 'Role', 'Action', 'Target Type', 'Status', 'Timestamp', 'IP Address'])
        
        for log, user in logs:
            ws.append([
                log.id,
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.role if user else '',
                log.action,
                log.target_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-disposition": f"attachment; filename={log_type}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
    )


def export_logs_pdf(logs, log_type):
    """Export logs as PDF file."""
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    
    elements.append(Paragraph(f"{log_type.capitalize()} Audit Logs Export", title_style))
    elements.append(Spacer(1, 12))
    
    if log_type == 'student':
        data = [['ID', 'Student Name', 'Email', 'Action', 'Related Type', 'Status', 'Timestamp', 'IP Address']]
        
        for log, student, user in logs:
            data.append([
                str(log.id),
                f"{user.first_name} {user.last_name}",
                user.email,
                log.action,
                log.related_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    elif log_type == 'office':
        data = [['ID', 'Admin Name', 'Email', 'Office', 'Login Time', 'Logout Time', 'Duration', 'Status', 'IP Address']]
        
        for log, office_admin, user, office in logs:
            data.append([
                str(log.id),
                f"{user.first_name} {user.last_name}",
                user.email,
                office.name,
                log.login_time.strftime('%Y-%m-%d %H:%M:%S'),
                log.logout_time.strftime('%Y-%m-%d %H:%M:%S') if log.logout_time else '',
                str(log.session_duration) + ' sec' if log.session_duration else '',
                'Success' if log.is_success else 'Failed',
                log.ip_address or ''
            ])
            
    elif log_type == 'superadmin':
        data = [['ID', 'Admin Name', 'Email', 'Action', 'Target Type', 'Status', 'Timestamp', 'IP Address']]
        
        for log, user in logs:
            data.append([
                str(log.id),
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.email if user else '',
                log.action,
                log.target_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
            
    else:  # 'all' or any other value
        data = [['ID', 'User', 'Role', 'Action', 'Target Type', 'Status', 'Timestamp', 'IP Address']]
        
        for log, user in logs:
            data.append([
                str(log.id),
                f"{user.first_name} {user.last_name}" if user else 'Unknown',
                user.role if user else '',
                log.action,
                log.target_type or '',
                'Success' if log.is_success else 'Failed',
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.ip_address or ''
            ])
    
    # Create the table with appropriate styling
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-disposition": f"attachment; filename={log_type}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
    )