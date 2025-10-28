from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, desc, asc, func

from app.office import office_bp
from app.utils import role_required
from app.extensions import db
from app.models import Feedback, CounselingSession, Student, User, OfficeAdmin


def _parse_date(value: str, end_of_day: bool = False):
    if not value:
        return None
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        if end_of_day:
            # move to end of day for inclusive filtering
            return dt + timedelta(days=1) - timedelta(seconds=1)
        return dt
    except Exception:
        return None


@office_bp.route('/feedbacks')
@login_required
@role_required(['office_admin'])
def office_feedbacks():
    """List student feedback for counseling sessions that belong to the current office.

    Filters (query params):
      - q: keyword search in student name or feedback message
      - date_from, date_to: filter by feedback.created_at date range (YYYY-MM-DD)
      - sort: one of ['newest', 'oldest'] by feedback.created_at
      - page: page number (default 1)
    """
    # Ensure the current user is tied to an office
    office_admin = OfficeAdmin.query.filter_by(user_id=current_user.id).first()
    if not office_admin:
        flash('Access denied: You are not assigned to any office.', 'error')
        return redirect(url_for('main.index'))

    office_id = office_admin.office_id

    # Inputs
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    per_page = max(5, min(per_page, 50))

    q = (request.args.get('q') or '').strip()
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'), end_of_day=True)
    sort = (request.args.get('sort') or 'newest').lower()

    # Base query: feedback for sessions belonging to this office
    query = (
        Feedback.query
        .join(CounselingSession, Feedback.session_id == CounselingSession.id)
        .join(Student, Feedback.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .filter(CounselingSession.office_id == office_id)
    )

    # Apply filters
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.first_name.ilike(like),
                                 User.last_name.ilike(like),
                                 Feedback.message.ilike(like)))

    if date_from:
        query = query.filter(Feedback.created_at >= date_from)
    if date_to:
        query = query.filter(Feedback.created_at <= date_to)

    # Sorting
    if sort == 'oldest':
        query = query.order_by(asc(Feedback.created_at))
    else:
        # default newest first
        query = query.order_by(desc(Feedback.created_at))

    # Pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    # Pre-compute derived data for template
    feedback_rows = []
    for f in items:
        try:
            student_user = getattr(f.student, 'user', None)
            sess = f.session
            feedback_rows.append({
                'id': f.id,
                'created_at': f.created_at,
                'message': f.message,
                'student_full_name': student_user.get_full_name() if student_user and hasattr(student_user, 'get_full_name') else 'Student',
                'student_profile_pic_path': student_user.profile_pic_path if student_user else None,
                'session_datetime': getattr(sess, 'scheduled_at', None),
                'session_status': getattr(sess, 'status', None),
                'session_id': getattr(sess, 'id', None),
            })
        except Exception:
            feedback_rows.append({
                'id': getattr(f, 'id', None),
                'created_at': getattr(f, 'created_at', None),
                'message': getattr(f, 'message', ''),
                'student_full_name': 'Student',
                'student_profile_pic_path': None,
                'session_datetime': None,
                'session_status': None,
                'session_id': None,
            })

    return render_template(
        'office/office_feedbacks.html',
        feedbacks=feedback_rows,
        pagination=pagination,
        q=q,
        date_from=request.args.get('date_from') or '',
        date_to=request.args.get('date_to') or '',
        sort=sort,
    )
