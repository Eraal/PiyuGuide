from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog, Department
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_, desc
import random
import os
from app.admin import admin_bp
from app.utils.decorators import campus_access_required
from io import StringIO, BytesIO
import csv

try:
    # Optional dependencies for richer exports
    from openpyxl import Workbook
except Exception:  # pragma: no cover
    Workbook = None

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
except Exception:  # pragma: no cover
    SimpleDocTemplate = None

@admin_bp.route('/admin_inquiries')
@login_required
@campus_access_required
def all_inquiries():
    """
    View all inquiries across offices (Superadmin only)
    This is a read-only view for monitoring purposes
    """
    office_id = request.args.get('office', type=int)
    status = request.args.get('status')
    department_id = request.args.get('department', type=int)
    date_range = request.args.get('date_range')
    search_query = request.args.get('search')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    query = _build_inquiries_query(request.args)
    # Extract current department for template state
    department_id = request.args.get('department', type=int)

    # Limit office choices shown in filter: campus admins (role super_admin) should only
    # see offices belonging to their assigned campus; higher roles (e.g., super_super_admin)
    # can still see all offices.
    if current_user.role == 'super_admin' and current_user.campus_id:
        offices = Office.query.filter(Office.campus_id == current_user.campus_id).all()
        # Only departments within the same campus
        departments = Department.query.filter(Department.campus_id == current_user.campus_id).order_by(Department.name.asc()).all()
    else:
        offices = Office.query.all()
        departments = Department.query.order_by(Department.name.asc()).all()
    
    query = query.order_by(desc(Inquiry.created_at))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    inquiries = pagination.items

    # Build filter params for pagination links (exclude 'page' to avoid duplicate keys)
    filters = {k: v for k, v in request.args.items() if k != 'page' and v not in (None, '')}

    # Stats reflect current filters (ignoring date_range for week-over-week comparisons)
    stats = get_inquiry_stats(request.args)
    
    return render_template(
        'admin/all_inquiries.html',
        inquiries=inquiries,
        pagination=pagination,
        offices=offices,
        stats=stats,
        departments=departments,
        current_department=department_id,
        filters=filters
    )


@admin_bp.route('/admin/api/inquiries-per-department')
@login_required
def inquiries_per_department():
    """Return JSON of inquiry counts grouped by department for the current campus context.

    If the user is a super_admin with a campus, results are scoped to that campus via Office.campus_id.
    Only structured departments (Student.department_id referencing Department) are counted.
    """
    # Base query with joins
    q = db.session.query(
        Department.id.label('department_id'),
        Department.name.label('department_name'),
        db.func.count(Inquiry.id).label('inquiry_count')
    ).join(
        Student, Student.department_id == Department.id
    ).join(
        Inquiry, Inquiry.student_id == Student.id
    ).join(
        Office, Office.id == Inquiry.office_id
    )

    # Scope to campus for campus admins
    if current_user.role == 'super_admin' and current_user.campus_id:
        q = q.filter(Office.campus_id == current_user.campus_id)

    q = q.group_by(Department.id, Department.name).order_by(Department.name.asc())

    rows = q.all()
    data = [
        {
            'department_id': row.department_id,
            'department_name': row.department_name,
            'count': int(row.inquiry_count or 0)
        }
        for row in rows
    ]

    return jsonify({'data': data})

def get_inquiry_stats(params=None):
    """Calculate inquiry statistics for the dashboard using current filters (excluding date filters).

    Args:
        params: dict-like of current filters (e.g., request.args). Date filters are ignored here
                so we can compute week-over-week comparisons consistently under the same constraints.
    """
    # Build base query with current filters but ignore date filters
    # Build on the same filtered query (helper already joins Office/Student/User and scopes campus)
    base = _build_inquiries_query(params or {}, ignore_dates=True)

    total = base.count()
    pending = base.filter(Inquiry.status == 'pending').count()
    in_progress = base.filter(Inquiry.status == 'in_progress').count()
    resolved = base.filter(Inquiry.status == 'resolved').count()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = today - timedelta(days=today.weekday())
    
    start_of_last_week = start_of_week - timedelta(days=7)
    end_of_last_week = start_of_week - timedelta(seconds=1)
    
    this_week_total = base.filter(Inquiry.created_at >= start_of_week).count()
    
    last_week_total = base.filter(
        Inquiry.created_at >= start_of_last_week,
        Inquiry.created_at <= end_of_last_week
    ).count()

    if last_week_total > 0:
        total_change = ((this_week_total - last_week_total) / last_week_total) * 100
    else:
        total_change = 100 if this_week_total > 0 else 0
    
    this_week_pending = base.filter(
        Inquiry.created_at >= start_of_week,
        Inquiry.status == 'pending'
    ).count()
    
    last_week_pending = base.filter(
        Inquiry.created_at >= start_of_last_week,
        Inquiry.created_at <= end_of_last_week,
        Inquiry.status == 'pending'
    ).count()
    
    if last_week_pending > 0:
        pending_change = ((this_week_pending - last_week_pending) / last_week_pending) * 100
    else:
        pending_change = 100 if this_week_pending > 0 else 0
    
    this_week_in_progress = base.filter(
        Inquiry.created_at >= start_of_week,
        Inquiry.status == 'in_progress'
    ).count()
    
    last_week_in_progress = base.filter(
        Inquiry.created_at >= start_of_last_week,
        Inquiry.created_at <= end_of_last_week,
        Inquiry.status == 'in_progress'
    ).count()
    
    if last_week_in_progress > 0:
        in_progress_change = ((this_week_in_progress - last_week_in_progress) / last_week_in_progress) * 100
    else:
        in_progress_change = 100 if this_week_in_progress > 0 else 0
    
    this_week_resolved = base.filter(
        Inquiry.created_at >= start_of_week,
        Inquiry.status == 'resolved'
    ).count()
    
    last_week_resolved = base.filter(
        Inquiry.created_at >= start_of_last_week,
        Inquiry.created_at <= end_of_last_week,
        Inquiry.status == 'resolved'
    ).count()
    
    if last_week_resolved > 0:
        resolved_change = ((this_week_resolved - last_week_resolved) / last_week_resolved) * 100
    else:
        resolved_change = 100 if this_week_resolved > 0 else 0
    
    # Return all stats
    return {
        'total': total,
        'pending': pending,
        'in_progress': in_progress,
        'resolved': resolved,
        'total_change': round(total_change),
        'pending_change': round(pending_change),
        'in_progress_change': round(in_progress_change),
        'resolved_change': round(resolved_change)
    }

@admin_bp.route('/admin/inquiry/<int:inquiry_id>')
@login_required
def view_inquiry_details(inquiry_id):
    """
    View detailed information about a specific inquiry
    This is for the modal popup when clicking on an inquiry
    """
    inquiry = Inquiry.query.get_or_404(inquiry_id)

    # Fix: Use proper query instead of trying to sort the InstrumentedList
    messages = InquiryMessage.query.filter_by(inquiry_id=inquiry_id).order_by(InquiryMessage.created_at).all() if hasattr(inquiry, 'messages') else []
    
    return render_template(
        'admin/inquiry_details_modal.html',
        inquiry=inquiry,
        messages=messages
    )

@admin_bp.route('/admin/inquiry/export', methods=['POST'])
@login_required
def export_inquiries():
    """
    Export filtered inquiries data in various formats
    """
    # Accept form-encoded or JSON payload
    payload = request.form if request.form else (request.get_json(silent=True) or {})
    export_format = (payload.get('format') or 'csv').lower()

    # Build the same filtered query used in the page
    query = _build_inquiries_query(payload)

    # Common headers
    headers = ['Inquiry ID', 'Student Name', 'Student ID', 'Department', 'Office', 'Subject', 'Status', 'Created At']

    # Prepare filename
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename_base = f"inquiries_{timestamp}"

    if export_format == 'csv':
        def generate():
            # UTF-8 BOM for Excel friendliness
            yield b"\xef\xbb\xbf"
            # Header row
            header_io = StringIO()
            csv.writer(header_io).writerow(headers)
            yield header_io.getvalue().encode('utf-8')
            header_io.close()
            # Stream rows
            for inq in query.order_by(desc(Inquiry.created_at)).yield_per(1000):
                student = getattr(inq, 'student', None)
                user = getattr(student, 'user', None) if student else None
                dept_name = student.department_name if student else ''
                row_io = StringIO()
                csv.writer(row_io).writerow([
                    f"INQ-{inq.id}",
                    user.get_full_name() if user else '',
                    student.student_number if student else '',
                    dept_name or '',
                    inq.office.name if inq.office else '',
                    inq.subject,
                    inq.status,
                    inq.created_at.strftime('%Y-%m-%d %H:%M:%S') if inq.created_at else ''
                ])
                yield row_io.getvalue().encode('utf-8')
                row_io.close()
        return Response(
            generate(),
            headers={
                'Content-Disposition': f'attachment; filename={filename_base}.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
    elif export_format == 'excel':
        if not Workbook:
            return jsonify({'error': 'Excel export not available'}), 400
        # Guard against very large exports
        try:
            total_rows = query.count()
            if total_rows > 50000:
                return jsonify({'error': 'Too many rows for Excel export. Please narrow your filters or use CSV.'}), 400
        except Exception:
            pass
        wb = Workbook()
        ws = wb.active
        ws.title = 'Inquiries'
        ws.append(headers)
        for inq in query.order_by(desc(Inquiry.created_at)).all():
            student = inq.student
            user = student.user if student else None
            dept_name = student.department_name if student else ''
            ws.append([
                f"INQ-{inq.id}",
                user.get_full_name() if user else '',
                student.student_number if student else '',
                dept_name or '',
                inq.office.name if inq.office else '',
                inq.subject,
                inq.status,
                inq.created_at.strftime('%Y-%m-%d %H:%M:%S') if inq.created_at else ''
            ])
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        return Response(
            bio.getvalue(),
            headers={
                'Content-Disposition': f'attachment; filename={filename_base}.xlsx',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )
    elif export_format == 'pdf':
        if not SimpleDocTemplate:
            return jsonify({'error': 'PDF export not available'}), 400
        try:
            total_rows = query.count()
            if total_rows > 10000:
                return jsonify({'error': 'Too many rows for PDF export. Please narrow your filters or use CSV.'}), 400
        except Exception:
            pass
        bio = BytesIO()
        doc = SimpleDocTemplate(bio, pagesize=landscape(letter))
        data = [headers]
        for inq in query.order_by(desc(Inquiry.created_at)).all():
            student = inq.student
            user = student.user if student else None
            dept_name = student.department_name if student else ''
            data.append([
                f"INQ-{inq.id}",
                user.get_full_name() if user else '',
                student.student_number if student else '',
                dept_name or '',
                inq.office.name if inq.office else '',
                inq.subject,
                inq.status,
                inq.created_at.strftime('%Y-%m-%d %H:%M:%S') if inq.created_at else ''
            ])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey)
        ]))
        doc.build([table])
        bio.seek(0)
        return Response(
            bio.getvalue(),
            headers={
                'Content-Disposition': f'attachment; filename={filename_base}.pdf',
                'Content-Type': 'application/pdf'
            }
        )

    return jsonify({'error': 'Export format not supported'}), 400


def _build_inquiries_query(params, ignore_dates: bool = False):
    """Build a filtered SQLAlchemy query for inquiries based on provided params.

    Params can be request.args, request.form, or a dict-like object.
    Applies campus scoping for campus admins.
    """
    # Extract fields (support both dict and MultiDict)
    get = params.get
    office_id = _to_int(get('office'))
    status = get('status')
    department_id = _to_int(get('department'))
    date_range = get('date_range')
    search_query = get('search')
    start_date = get('start_date')
    end_date = get('end_date')

    query = Inquiry.query\
        .join(Student, Inquiry.student)\
        .join(User, Student.user)\
        .join(Office, Inquiry.office)

    # Campus scoping for campus admins
    if current_user.role == 'super_admin' and current_user.campus_id:
        query = query.filter(Office.campus_id == current_user.campus_id)

    if office_id:
        query = query.filter(Inquiry.office_id == office_id)

    if status:
        query = query.filter(Inquiry.status == status)

    if department_id:
        query = query.filter(Student.department_id == department_id)

    # Date filters
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not ignore_dates and date_range == 'today':
        query = query.filter(Inquiry.created_at >= today)
    elif not ignore_dates and date_range == 'yesterday':
        yesterday = today - timedelta(days=1)
        query = query.filter(Inquiry.created_at >= yesterday, Inquiry.created_at < today)
    elif not ignore_dates and date_range == 'this_week':
        start_of_week = today - timedelta(days=today.weekday())
        query = query.filter(Inquiry.created_at >= start_of_week)
    elif not ignore_dates and date_range == 'last_week':
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = start_of_last_week + timedelta(days=7)
        query = query.filter(Inquiry.created_at >= start_of_last_week, Inquiry.created_at < end_of_last_week)
    elif not ignore_dates and date_range == 'this_month':
        start_of_month = today.replace(day=1)
        query = query.filter(Inquiry.created_at >= start_of_month)
    elif not ignore_dates and date_range == 'last_month':
        last_month = today.replace(day=1) - timedelta(days=1)
        start_of_last_month = last_month.replace(day=1)
        query = query.filter(Inquiry.created_at >= start_of_last_month, Inquiry.created_at < today.replace(day=1))
    elif not ignore_dates and date_range == 'custom':
        if start_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Inquiry.created_at >= sd)
            except ValueError:
                pass
        if end_date:
            try:
                ed = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Inquiry.created_at < ed)
            except ValueError:
                pass

    if search_query:
        search = f"%{search_query}%"
        query = query.outerjoin(InquiryMessage, Inquiry.id == InquiryMessage.inquiry_id).filter(
            or_(
                User.first_name.ilike(search),
                User.last_name.ilike(search),
                Student.student_number.ilike(search),
                Inquiry.subject.ilike(search),
                InquiryMessage.content.ilike(search)
            )
        ).distinct()

    return query


def _to_int(value):
    try:
        return int(value) if value not in (None, '',) else None
    except (TypeError, ValueError):
        return None