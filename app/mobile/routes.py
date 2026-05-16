from datetime import datetime, timedelta

from flask import current_app, jsonify, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import desc
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, socketio
from app.models import (
    AuditLog, Campus, Department, Inquiry, InquiryMessage, Notification,
    Office, OfficeAdmin, Student, User, ConcernType, OfficeConcernType,
    InquiryConcern, StudentActivityLog
)

from . import mobile_bp


def _json_error(message: str, status: int = 400, **extra):
    payload = {'success': False, 'message': message}
    payload.update(extra)
    return jsonify(payload), status


def _absolute_static_url(relative_path: str | None):
    if not relative_path:
        return None
    try:
        return url_for('static', filename=relative_path, _external=True)
    except Exception:
        return url_for('static', filename=relative_path)


def _serialize_user(user: User):
    campus_id = getattr(user, 'campus_id', None)
    campus_name = None
    student_data = None

    if getattr(user, 'student', None):
        student = user.student
        campus_id = student.campus_id or campus_id
        if getattr(student, 'campus', None):
            campus_name = student.campus.name
        elif student.campus_id:
            campus = Campus.query.get(student.campus_id)
            campus_name = campus.name if campus else None
        student_data = {
            'id': student.id,
            'student_number': student.student_number,
            'department': student.department_name,
            'department_id': student.department_id,
            'year_level': student.year_level,
            'section': student.section,
            'campus_id': student.campus_id,
        }
    elif getattr(user, 'office_admin', None) and getattr(user.office_admin, 'office', None):
        office = user.office_admin.office
        campus_id = office.campus_id or campus_id
        campus = Campus.query.get(office.campus_id) if office.campus_id else None
        campus_name = campus.name if campus else None
    elif getattr(user, 'campus_id', None):
        campus = Campus.query.get(user.campus_id)
        campus_name = campus.name if campus else None

    profile_pic_path = getattr(user, 'profile_pic_path', None)

    return {
        'id': user.id,
        'full_name': user.get_full_name(),
        'email': user.email,
        'role': user.role,
        'is_active': user.is_active,
        'is_online': user.is_online,
        'email_verified': user.email_verified,
        'campus_id': campus_id,
        'campus_name': campus_name,
        'profile_pic_url': _absolute_static_url(profile_pic_path) if profile_pic_path else None,
        'student': student_data,
    }


def _record_auth_log(user: User | None, action: str, success: bool, failure_reason: str | None = None):
    if not user:
        return

    db.session.add(
        AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            action=action,
            target_type='authentication',
            status_snapshot='success' if success else 'failed',
            is_success=success,
            failure_reason=failure_reason,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
        )
    )


def _serialize_message(message: InquiryMessage, viewer_user_id: int | None = None):
    sender = message.sender
    attachments_payload = []

    for attachment in (message.attachments or []):
        attachments_payload.append({
            'filename': attachment.filename,
            'file_path': attachment.file_path,
            'file_type': attachment.file_type,
            'file_size': attachment.file_size,
        })

    avatar_url = None
    if sender and getattr(sender, 'profile_pic_path', None):
        avatar_url = _absolute_static_url(sender.profile_pic_path)

    return {
        'id': message.id,
        'content': message.content or '',
        'timestamp': message.created_at.strftime('%Y-%m-%d %H:%M:%S') if message.created_at else datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'sender_name': sender.get_full_name() if sender else 'Unknown',
        'sender_role': sender.role if sender else None,
        'sender_avatar_url': avatar_url,
        'is_current_user': bool(viewer_user_id and message.sender_id == viewer_user_id),
        'status': message.status,
        'attachments': attachments_payload,
    }


def _campus_short_name(campus: Campus):
    campus_name = (campus.name or '').strip()
    prefix = 'Laguna State Polytechnic University - '
    if campus_name.startswith(prefix):
        return campus_name[len(prefix):].strip() or campus_name
    if ' - ' in campus_name:
        return campus_name.split(' - ', 1)[1].strip() or campus_name
    return campus_name


def _serialize_campus(campus: Campus):
    return {
        'id': campus.id,
        'name': campus.name,
        'short_name': _campus_short_name(campus),
        'code': campus.code,
        'address': campus.address,
        'description': campus.description,
        'theme_key': campus.campus_theme_key or 'blue',
    }


def _serialize_department(department: Department):
    return {
        'id': department.id,
        'name': department.name,
        'code': department.code,
        'description': department.description,
    }


def _serialize_inquiry_summary(inquiry: Inquiry):
    latest_message = inquiry.messages[-1] if inquiry.messages else None
    latest_message_preview = None
    latest_message_at = None

    if latest_message:
        latest_message_preview = (latest_message.content or '')[:120]
        latest_message_at = latest_message.created_at.strftime('%Y-%m-%d %H:%M:%S') if latest_message.created_at else None

    office = inquiry.office

    return {
        'id': inquiry.id,
        'subject': inquiry.subject,
        'status': inquiry.status,
        'office_id': office.id if office else None,
        'office_name': office.name if office else None,
        'campus_id': office.campus_id if office else None,
        'created_at': inquiry.created_at.strftime('%Y-%m-%d %H:%M:%S') if inquiry.created_at else None,
        'updated_at': latest_message_at or (inquiry.created_at.strftime('%Y-%m-%d %H:%M:%S') if inquiry.created_at else None),
        'latest_message_preview': latest_message_preview,
        'latest_message_at': latest_message_at,
    }


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_full_name(full_name: str):
    parts = [part for part in full_name.split() if part]
    if len(parts) < 2:
        return None, None
    return parts[0], ' '.join(parts[1:])


def _sanitize_section(section_value: str | None):
    if not section_value:
        return None

    import re

    match = re.search(r'([A-E])', section_value.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _get_authenticated_student():
    if not current_user.is_authenticated:
        return None, _json_error('Authentication required.', 401)

    if current_user.role != 'student':
        return None, _json_error('Student access required.', 403)

    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        return None, _json_error('Student profile not found.', 404)

    return student, None


@mobile_bp.route('/select-campus', methods=['POST'])
def select_campus():
    payload = request.get_json(silent=True) or request.form
    campus_id = _parse_int(payload.get('campus_id'))

    if not campus_id:
        return _json_error('Campus selection is required.', 400)

    campus = Campus.query.filter_by(id=campus_id, is_active=True).first()
    if not campus:
        return _json_error('Selected campus not found.', 404)

    session['selected_campus_id'] = campus.id

    return jsonify({
        'success': True,
        'message': 'Campus selected.',
        'campus': _serialize_campus(campus),
    })


@mobile_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return _json_error('Email and password are required.', 400)

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        _record_auth_log(user, 'Failed mobile login attempt', False, 'Invalid credentials')
        if user:
            db.session.commit()
        return _json_error('Invalid email or password.', 401)

    if (not user.is_active) or getattr(user, 'account_locked', False):
        reason = user.lock_reason or 'Your account has been suspended.'
        _record_auth_log(user, 'Blocked mobile login attempt', False, reason)
        db.session.commit()
        return _json_error(reason, 403)

    if user.role not in {'student', 'office_admin', 'super_admin', 'super_super_admin'}:
        _record_auth_log(user, 'Blocked mobile login attempt', False, 'Unknown user role')
        db.session.commit()
        return _json_error('Unknown user role.', 403)

    if user.role == 'student' and not getattr(user, 'email_verified', False):
        try:
            from app.auth.routes import _issue_and_send_verification

            if not user.email_verification_sent_at or (datetime.utcnow() - user.email_verification_sent_at) > timedelta(minutes=5):
                _issue_and_send_verification(user)
                db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Please verify your email before signing in.',
            'needs_verification': True,
        }), 403

    user.is_online = True
    user.last_activity = datetime.utcnow()
    login_user(user)

    if user.role == 'student' and getattr(user, 'student', None) and user.student.campus_id:
        session['selected_campus_id'] = user.student.campus_id
    elif user.role == 'super_admin' and user.campus_id:
        session['selected_campus_id'] = user.campus_id

    _record_auth_log(user, 'Logged in', True)

    if user.role == 'office_admin' and user.office_admin:
        try:
            from app.models import OfficeLoginLog

            OfficeLoginLog.log_login(
                office_admin=user.office_admin,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
            )
        except Exception:
            pass

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Login successful.',
        'user': _serialize_user(user),
        'selected_campus_id': session.get('selected_campus_id'),
    })


@mobile_bp.route('/register', methods=['POST'])
def register():
    payload = request.get_json(silent=True) or request.form

    full_name = (payload.get('full_name') or payload.get('name') or '').strip()
    first_name = (payload.get('first_name') or '').strip()
    last_name = (payload.get('last_name') or '').strip()
    email = (payload.get('email') or '').strip().lower()
    password = payload.get('password') or ''
    confirm_password = payload.get('confirm_password') or payload.get('confirmPassword') or ''
    student_number = (payload.get('student_number') or payload.get('studentNumber') or '').strip()
    year_level = (payload.get('year_level') or payload.get('yearLevel') or '').strip()
    section = _sanitize_section(payload.get('section'))
    campus_id = _parse_int(payload.get('campus_id') or session.get('selected_campus_id'))
    department_id = _parse_int(payload.get('department_id') or payload.get('departmentId'))

    if (not first_name or not last_name) and full_name:
        split_first_name, split_last_name = _split_full_name(full_name)
        first_name = first_name or (split_first_name or '')
        last_name = last_name or (split_last_name or '')

    if not first_name or not last_name or not email or not password:
        return _json_error('First name, last name, email, and password are required.', 400)

    if not student_number or not department_id or not year_level or not section:
        return _json_error('Student number, department, year level, and section are required.', 400)

    if not email.endswith('@lspu.edu.ph'):
        return _json_error('Please use your institutional email address.', 400)

    import re

    if not re.match(r'^\d{4}-\d{4}$', student_number):
        return _json_error('Student number must be in format NNNN-NNNN.', 400)

    if User.query.filter_by(email=email).first():
        return _json_error('This institutional email is already in use.', 409)

    if Student.query.filter_by(student_number=student_number).first():
        return _json_error('This student number is already registered.', 409)

    if password != confirm_password:
        return _json_error('Passwords do not match.', 400)

    if not campus_id:
        return _json_error('Please select a campus before registering.', 400)

    campus = Campus.query.filter_by(id=campus_id, is_active=True).first()
    if not campus:
        return _json_error('Selected campus not found.', 404)

    department = Department.query.filter_by(id=department_id, campus_id=campus.id, is_active=True).first()
    if not department:
        return _json_error('Selected department is invalid for this campus.', 400)

    new_user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        role='student',
        password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        is_active=True,
        email_verified=False,
    )

    try:
        db.session.add(new_user)
        db.session.flush()

        student = Student(
            user_id=new_user.id,
            student_number=student_number,
            department=department.name,
            department_id=department.id,
            year_level=year_level,
            section=section,
            campus_id=campus.id,
        )
        db.session.add(student)
        session['selected_campus_id'] = campus.id
        db.session.commit()

        created_user = User.query.get(new_user.id)
        verification_message = 'Registration successful. Please check your email to verify your account.'

        try:
            from app.auth.routes import _issue_and_send_verification

            _issue_and_send_verification(created_user or new_user)
        except Exception:
            verification_message = 'Registration successful, but we could not send the verification email right now.'
            try:
                current_app.logger.exception('Failed to send mobile registration verification email')
            except Exception:
                pass
        finally:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

        return jsonify({
            'success': True,
            'message': verification_message,
            'needs_verification': True,
            'selected_campus_id': session.get('selected_campus_id'),
            'user': _serialize_user(created_user or new_user),
        })
    except Exception:
        db.session.rollback()
        return _json_error('An error occurred while creating your account. Please try again.', 500)


@mobile_bp.route('/logout', methods=['POST'])
def logout():
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_activity = datetime.utcnow()
        _record_auth_log(current_user, 'Logged out', True)
        if current_user.role == 'office_admin' and current_user.office_admin:
            try:
                from app.models import OfficeLoginLog

                login_log = OfficeLoginLog.query.filter_by(
                    office_admin_id=current_user.office_admin.id,
                    logout_time=None,
                ).order_by(OfficeLoginLog.login_time.desc()).first()
                if login_log:
                    login_log.update_logout()
            except Exception:
                pass
        db.session.commit()

    logout_user()
    session.pop('selected_campus_id', None)
    return jsonify({'success': True, 'message': 'Logged out.'})


@mobile_bp.route('/me', methods=['GET'])
def me():
    if not current_user.is_authenticated:
        return _json_error('Authentication required.', 401)

    return jsonify({'success': True, 'user': _serialize_user(current_user)})


@mobile_bp.route('/notifications', methods=['GET'])
def get_notifications():
    student, error = _get_authenticated_student()
    if error:
        return error

    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(desc(Notification.created_at)).limit(50).all()
    
    return jsonify({
        'success': True,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'notification_type': n.notification_type,
            'inquiry_id': n.inquiry_id,
            'source_office_id': n.source_office_id,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S') if n.created_at else None,
            'link': n.link
        } for n in notifications]
    })


@mobile_bp.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    if not current_user.is_authenticated:
        return _json_error('Authentication required.', 401)

    payload = request.get_json(silent=True) or request.form
    notification_id = _parse_int(payload.get('notification_id'))

    if notification_id:
        notif = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
        if notif:
            notif.is_read = True
    else:
        # Mark all as read
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    
    db.session.commit()
    return jsonify({'success': True})


@mobile_bp.route('/campuses', methods=['GET'])
def campuses():
    campuses_query = Campus.query.filter_by(is_active=True).order_by(Campus.name.asc()).all()
    return jsonify({
        'success': True,
        'campuses': [_serialize_campus(campus) for campus in campuses_query],
    })


@mobile_bp.route('/campuses/<int:campus_id>/departments', methods=['GET'])
def campus_departments(campus_id: int):
    departments = Department.query.filter_by(campus_id=campus_id, is_active=True).order_by(Department.name.asc()).all()
    return jsonify({
        'success': True,
        'departments': [_serialize_department(department) for department in departments],
    })


@mobile_bp.route('/inquiries', methods=['GET'])
def inquiries():
    student, error = _get_authenticated_student()
    if error:
        return error

    inquiries_query = Inquiry.query.filter_by(student_id=student.id).order_by(desc(Inquiry.created_at)).all()
    return jsonify({
        'success': True,
        'inquiries': [_serialize_inquiry_summary(inquiry) for inquiry in inquiries_query],
    })


@mobile_bp.route('/inquiry/<int:inquiry_id>/messages', methods=['GET', 'POST'])
def inquiry_messages(inquiry_id: int):
    student, error = _get_authenticated_student()
    if error:
        return error

    inquiry = Inquiry.query.filter_by(id=inquiry_id, student_id=student.id).first()
    if not inquiry:
        return _json_error('Inquiry not found.', 404)

    if request.method == 'GET':
        before_id = request.args.get('before_id', type=int)
        limit = request.args.get('limit', 50, type=int)

        query = InquiryMessage.query.filter_by(inquiry_id=inquiry.id)
        if before_id:
            oldest_message = InquiryMessage.query.get(before_id)
            if oldest_message:
                query = query.filter(InquiryMessage.created_at < oldest_message.created_at)

        messages = query.order_by(desc(InquiryMessage.created_at)).limit(limit).all()
        messages = messages[::-1]

        return jsonify({
            'success': True,
            'messages': [_serialize_message(message, current_user.id) for message in messages],
            'has_more': len(messages) >= limit,
        })

    payload = request.get_json(silent=True) or request.form
    content = (payload.get('message') or payload.get('content') or '').strip()
    client_msg_id = payload.get('client_msg_id') or payload.get('clientMsgId')

    # Collect uploaded files (multipart/form-data support)
    uploaded_files = request.files.getlist('attachments') if 'attachments' in request.files else []

    if (inquiry.status or '').lower() == 'closed':
        return _json_error('This inquiry is closed. Further messages are disabled.', 400)

    if not content and not any(f.filename for f in uploaded_files):
        return _json_error('Message or attachment is required.', 400)

    new_message = InquiryMessage(
        inquiry_id=inquiry.id,
        sender_id=current_user.id,
        content=content,
        status='sent',
        delivered_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.session.add(new_message)
    db.session.flush()

    # Process file attachments
    attachments_payload = []
    for file in uploaded_files:
        if not file or not file.filename:
            continue
        try:
            from app.utils.file_uploads import save_upload
            from werkzeug.utils import secure_filename as _sf
            static_path, meta = save_upload(file, subfolder='messages')
        except Exception:
            continue
        from app.models import MessageAttachment
        att = MessageAttachment(
            filename=meta.get('filename') or _sf(file.filename),
            file_path=static_path,
            file_size=meta.get('file_size'),
            file_type=meta.get('file_type') or (file.content_type if hasattr(file, 'content_type') else None),
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            message_id=new_message.id,
        )
        db.session.add(att)
        attachments_payload.append({
            'filename': att.filename,
            'file_path': att.file_path,
            'file_type': att.file_type,
            'file_size': att.file_size,
        })

    office = inquiry.office or Office.query.get(inquiry.office_id)
    office_admins = OfficeAdmin.query.filter_by(office_id=office.id).all() if office else []
    for admin in office_admins:
        db.session.add(Notification(
            user_id=admin.user_id,
            title='New Message',
            message=f"New message from {current_user.get_full_name()} in inquiry '{inquiry.subject}'",
            is_read=False,
            notification_type='inquiry_reply',
            inquiry_id=inquiry.id,
            source_office_id=office.id if office else None,
        ))

    payload_message = _serialize_message(new_message, current_user.id)
    # Inject attachments into the payload (they may not be loaded by the ORM yet)
    if attachments_payload:
        payload_message['attachments'] = attachments_payload
    if client_msg_id:
        payload_message['client_msg_id'] = client_msg_id

    db.session.commit()

    try:
        room = f'inquiry_{inquiry.id}'
        socketio.emit('receive_message', payload_message, room=room, namespace='/chat')
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message_id': new_message.id,
        'client_msg_id': client_msg_id,
        'message': payload_message,
    })


@mobile_bp.route('/offices', methods=['GET'])
def get_offices():
    student, error = _get_authenticated_student()
    if error:
        return error

    campus_id = student.campus_id or session.get('selected_campus_id')
    query = Office.query
    if campus_id:
        query = query.filter_by(campus_id=campus_id)
    
    offices = query.order_by(Office.name.asc()).all()

    return jsonify({
        'success': True,
        'offices': [{
            'id': o.id,
            'name': o.name,
            'description': o.description,
        } for o in offices]
    })


@mobile_bp.route('/offices/<int:office_id>/inquiry-natures', methods=['GET'])
def get_office_inquiry_natures(office_id):
    student, error = _get_authenticated_student()
    if error:
        return error

    concern_types = (
        ConcernType.query.join(OfficeConcernType)
        .filter(
            OfficeConcernType.office_id == office_id,
            OfficeConcernType.for_inquiries.is_(True)
        )
        .order_by(ConcernType.name)
        .all()
    )

    return jsonify({
        'success': True,
        'natures': [{
            'id': ct.id,
            'name': ct.name,
            'description': ct.description,
            'allows_other': ct.allows_other
        } for ct in concern_types]
    })


@mobile_bp.route('/inquiries/submit', methods=['POST'])
def submit_inquiry():
    student, error = _get_authenticated_student()
    if error:
        return error

    payload = request.get_json(silent=True) or request.form
    office_id = payload.get('office_id')
    subject = (payload.get('subject') or '').strip()
    message = (payload.get('message') or '').strip()
    concern_type_id = payload.get('concern_type_id')
    other_concern = payload.get('other_concern')

    if not office_id or not subject or not message:
        return _json_error('Office, subject, and message are required.', 400)

    try:
        office_id = int(office_id)
    except (TypeError, ValueError):
        return _json_error('Invalid office ID.', 400)

    office = Office.query.get(office_id)
    if not office:
        return _json_error('Selected office does not exist.', 404)

    campus_id = student.campus_id or session.get('selected_campus_id')
    if campus_id and office.campus_id != campus_id:
        return _json_error('You can only submit inquiries to offices in your campus.', 403)

    new_inquiry = Inquiry(
        student_id=student.id,
        office_id=office_id,
        subject=subject,
        status='pending',
        created_at=datetime.utcnow()
    )
    db.session.add(new_inquiry)
    db.session.flush()

    initial_message = InquiryMessage(
        inquiry_id=new_inquiry.id,
        sender_id=current_user.id,
        content=message,
        status='sent',
        created_at=datetime.utcnow(),
        delivered_at=datetime.utcnow()
    )
    db.session.add(initial_message)
    db.session.flush()

    if concern_type_id:
        try:
            concern_type_id = int(concern_type_id)
            assoc = OfficeConcernType.query.filter_by(
                office_id=office_id,
                concern_type_id=concern_type_id,
                for_inquiries=True
            ).first()
            concern_type = ConcernType.query.get(concern_type_id)
            if not assoc or not concern_type:
                db.session.rollback()
                return _json_error('Selected concern type is not available for inquiries in this office.', 400)
            
            concern = InquiryConcern(
                inquiry_id=new_inquiry.id,
                concern_type_id=concern_type_id,
                other_specification=other_concern if concern_type.allows_other and other_concern else None
            )
            db.session.add(concern)
        except (TypeError, ValueError):
            pass

    log_entry = StudentActivityLog.log_action(
        student=student,
        action="Created new inquiry via mobile",
        related_id=new_inquiry.id,
        related_type="inquiry",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    try:
        from app.utils.smart_notifications import SmartNotificationManager
        office_admin_user_ids = SmartNotificationManager.get_office_admin_for_notification(office_id)

        for admin_user_id in office_admin_user_ids:
            SmartNotificationManager.create_inquiry_notification(
                new_inquiry, admin_user_id, 'new_inquiry'
            )
    except Exception:
        pass

    try:
        concern_type_ids = [ic.concern_type_id for ic in InquiryConcern.query.filter_by(inquiry_id=new_inquiry.id).all()]
        if concern_type_ids:
            assoc = OfficeConcernType.query.filter(
                OfficeConcernType.office_id == new_inquiry.office_id,
                OfficeConcernType.concern_type_id.in_(concern_type_ids),
                OfficeConcernType.auto_reply_enabled.is_(True),
                OfficeConcernType.auto_reply_message.isnot(None)
            ).order_by(OfficeConcernType.id.asc()).first()
        else:
            assoc = None

        if assoc and assoc.auto_reply_message and assoc.auto_reply_message.strip():
            office_admin = OfficeAdmin.query.filter_by(office_id=new_inquiry.office_id).first()
            if office_admin:
                student_user = User.query.get(student.user_id)
                rendered = assoc.auto_reply_message
                try:
                    rendered = (
                        rendered
                        .replace('{{student_name}}', student_user.get_full_name() if student_user else 'Student')
                        .replace('{{office_name}}', office.name if office else 'Office')
                    )
                except Exception:
                    pass

                auto_msg = InquiryMessage(
                    inquiry_id=new_inquiry.id,
                    sender_id=office_admin.user_id,
                    content=rendered,
                    status='sent',
                    delivered_at=datetime.utcnow(),
                    created_at=datetime.utcnow()
                )
                db.session.add(auto_msg)

                db.session.add(Notification(
                    user_id=student.user_id,
                    title="New Office Reply",
                    message=f"New message from office in inquiry '{new_inquiry.subject}'",
                    is_read=False,
                    notification_type='inquiry_reply',
                    inquiry_id=new_inquiry.id,
                    source_office_id=new_inquiry.office_id
                ))
    except Exception as e:
        current_app.logger.error(f"Mobile auto-reply generation failed: {e}")

    db.session.commit()

    try:
        payload = {
            'id': new_inquiry.id,
            'subject': new_inquiry.subject,
            'status': new_inquiry.status,
            'student_name': current_user.get_full_name() if hasattr(current_user, 'get_full_name') else 'Student',
            'office_id': new_inquiry.office_id,
            'created_at': new_inquiry.created_at.isoformat(),
            'unread_count': 1,
        }
        socketio.emit('new_office_inquiry', payload, room=f"office_{new_inquiry.office_id}", namespace='/office')
    except Exception:
        pass

    return jsonify({
        'success': True,
        'inquiry_id': new_inquiry.id,
        'message': 'Inquiry created successfully.',
    })