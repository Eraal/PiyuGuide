from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc, or_
from app.student import student_bp
from app.models import (
    Announcement, Student, User, Office, 
    StudentActivityLog, Notification, AnnouncementImage
)
from app.extensions import db
from app.utils import role_required

@student_bp.route('/announcements')
@login_required
@role_required(['student'])
def announcements():
    """View announcements available to the student, with filters and pagination to mirror Admin/Office UI."""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()

    # Resolve campus context: prefer student's campus, fallback to session-selected campus
    campus_id = student.campus_id or session.get('selected_campus_id')

    # Query params for filters/pagination (align with admin/office semantics)
    office_id = request.args.get('office_id') or request.args.get('office')  # support either key
    visibility = request.args.get('visibility')  # 'public' | 'office' | ''
    date_range = request.args.get('date_range')  # 'today' | 'week' | 'month' | ''
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 10

    # First, determine offices the student has interacted with (for private/office announcements)
    from app.models import Inquiry
    inquiry_offices = (
        db.session.query(Inquiry.office_id)
        .filter_by(student_id=student.id)
        .distinct()
        .all()
    )
    office_ids = [oid for (oid,) in inquiry_offices]

    # Base visibility condition: public OR in student's offices
    q = Announcement.query

    # Constrain announcements to the student's campus (include global announcements without target office)
    if campus_id:
        q = (
            q.outerjoin(Office, Announcement.target_office_id == Office.id)
             .filter(
                 or_(Announcement.target_office_id.is_(None), Office.campus_id == campus_id)
             )
        )
    visibility_condition = (Announcement.is_public.is_(True))
    if office_ids:
        visibility_condition = visibility_condition | (Announcement.target_office_id.in_(office_ids))
    q = q.filter(visibility_condition)

    # Apply filters
    if office_id:
        try:
            office_id_int = int(office_id)
            q = q.filter(Announcement.target_office_id == office_id_int)
        except ValueError:
            pass

    if visibility == 'public':
        q = q.filter(Announcement.is_public.is_(True))
    elif visibility in ('office', 'private'):
        q = q.filter(Announcement.is_public.is_(False))

    if date_range in ('today', 'week', 'month'):
        now = datetime.utcnow()
        if date_range == 'today':
            # Announcements from today (UTC)
            from datetime import date
            start = datetime.combine(date.today(), datetime.min.time())
        elif date_range == 'week':
            from datetime import timedelta
            start = now - timedelta(days=7)
        else:  # 'month'
            from datetime import timedelta
            start = now - timedelta(days=30)
        q = q.filter(Announcement.created_at >= start)

    # Sorting newest first
    q = q.order_by(desc(Announcement.created_at))

    # Total count for pagination (before limit/offset)
    total_count = q.count()

    # Pagination window
    items = q.limit(per_page).offset((page - 1) * per_page).all()

    # Mark recent announcements (less than 3 days old)
    today = datetime.utcnow()
    new_announcements_count = 0
    for ann in items:
        is_new = (today - ann.created_at).days < 3
        ann.is_new = is_new
        if is_new:
            new_announcements_count += 1

    # Offices for filter dropdown
    # Offices for filter dropdown (limited to student's campus if available)
    if campus_id:
        offices = Office.query.filter_by(campus_id=campus_id).order_by(Office.name.asc()).all()
    else:
        offices = Office.query.order_by(Office.name.asc()).all()

    # Navbar notifications
    unread_notifications_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(5).all()

    # Pagination numbers for template (mirror admin)
    import math
    total_pages = max(math.ceil(total_count / per_page), 1)
    current_page = min(page, total_pages)
    prev_page = current_page - 1 if current_page > 1 else None
    next_page = current_page + 1 if current_page < total_pages else None

    # Log this activity
    log_entry = StudentActivityLog(
        student_id=student.id,
        action="Viewed announcements",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()

    return render_template(
        'student/announcements.html',
        announcements=items,
        offices=offices,
        new_announcements_count=new_announcements_count,
        total_announcements_count=total_count,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications,
        total_pages=total_pages,
        current_page=current_page,
        prev_page=prev_page,
        next_page=next_page,
        selected_office_id=int(office_id) if office_id and office_id.isdigit() else None,
        selected_visibility=visibility or '',
        selected_date_range=date_range or ''
    )

@student_bp.route('/announcement/<int:announcement_id>')
@login_required
@role_required(['student'])
def view_announcement(announcement_id):
    """View details for a specific announcement"""
    # Get the student record
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Get the announcement
    announcement = Announcement.query.get_or_404(announcement_id)
    
    # Check if student is allowed to see this announcement
    if not announcement.is_public:
        # Check if student has inquired to the office this announcement is for
        from app.models import Inquiry
        has_inquiry = Inquiry.query.filter_by(
            student_id=student.id,
            office_id=announcement.target_office_id
        ).first()
        
        if not has_inquiry:
            flash("You do not have permission to view this announcement", "error")
            return redirect(url_for('student.announcements'))
    
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
        action=f"Viewed announcement #{announcement_id}",
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log_entry)
    db.session.commit()
    
    return render_template(
        'student/view_announcement.html',
        announcement=announcement,
        unread_notifications_count=unread_notifications_count,
        notifications=notifications
    )


@student_bp.route('/api/announcement/<int:announcement_id>')
@login_required
@role_required(['student'])
def api_get_announcement(announcement_id: int):
    """Return full announcement details for modal display (student-safe).

    Enforces visibility rules: public announcements are visible; private (office) announcements
    require that the student has an inquiry with the target office.
    """
    # Get student
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()

    ann = Announcement.query.get_or_404(announcement_id)

    # Check visibility
    if not ann.is_public:
        from app.models import Inquiry
        has_inquiry = Inquiry.query.filter_by(
            student_id=student.id,
            office_id=ann.target_office_id
        ).first()
        if not has_inquiry:
            return jsonify({'error': 'Forbidden'}), 403

    # Build payload
    try:
        author = ann.author
        author_name = author.get_full_name() if author else 'System'
        author_role = getattr(author, 'role', 'system') if author else 'system'
        office_name = None
        posted_by_office_name = None
        campus_name = None
        try:
            # Target office (audience)
            if ann.target_office_id:
                office = Office.query.get(ann.target_office_id)
                office_name = office.name if office else None
                campus_name = office.campus.name if office and office.campus else None
            # Author's office (if office admin authored)
            if author_role == 'office_admin' and getattr(author, 'office_admin', None):
                posted_by_office_name = getattr(author.office_admin.office, 'name', None)
            elif author_role == 'super_admin':
                campus_name = getattr(author.campus, 'name', None) or campus_name
        except Exception:
            pass

        # Images
        images = (AnnouncementImage.query
                  .filter_by(announcement_id=ann.id)
                  .order_by(AnnouncementImage.display_order, AnnouncementImage.id)
                  .all())
        from flask import url_for as _url_for
        image_list = [
            {
                'id': img.id,
                'url': _url_for('static', filename=img.image_path),
                'caption': img.caption,
                'display_order': img.display_order
            }
            for img in images
        ]

        payload = {
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'is_public': bool(ann.is_public),
            'created_at_iso': ann.created_at.isoformat() if ann.created_at else None,
            'created_at': ann.created_at.strftime('%b %d, %Y %I:%M %p') if ann.created_at else None,
            'author_name': author_name,
            'author_role': author_role,
            'office_name': office_name,
            'posted_by_office_name': posted_by_office_name,
            'campus_name': campus_name,
            'images': image_list,
        }
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500