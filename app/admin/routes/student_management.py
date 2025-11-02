from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog, AccountLockHistory, Department
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_, and_, exists
import random
import os
from app.admin import admin_bp
from app.utils.decorators import campus_access_required
from flask_wtf.csrf import CSRFError

# New: activation/deactivation with reason modal support
@admin_bp.route('/toggle_student_status', methods=['POST'])
@login_required
def toggle_student_status():
    """Activate or deactivate (suspend) a student account with optional reason.

    Request JSON: { student_id: int, is_active: bool, reason: str (optional) }
    When deactivating (is_active false), reason is stored in user.lock_reason and account_locked is set.
    When activating, clears lock flags.
    """
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    try:
        data = request.get_json(silent=True) or {}
        student_id = data.get('student_id')
        is_active = data.get('is_active')
        reason = (data.get('reason') or '').strip()
        if student_id is None or is_active is None:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        user = student.user
        # Ensure same campus scope
        if getattr(current_user, 'campus_id', None) and student.campus_id != current_user.campus_id:
            return jsonify({'success': False, 'message': 'Campus mismatch'}), 403
        # Perform update
        if is_active:
            user.is_active = True
            user.account_locked = False
            user.lock_reason = None
            user.locked_at = None
            user.locked_by_id = None
            action_label = 'activated'
        else:
            user.is_active = False
            # Treat as suspension (reuse lock fields for auditability)
            user.account_locked = True
            user.lock_reason = reason or 'Suspended by administrator'
            user.locked_at = datetime.utcnow()
            user.locked_by_id = current_user.id
            action_label = 'deactivated'
        # Activity / audit logs
        try:
            reason_text = user.lock_reason or ''
            SuperAdminActivityLog.log_action(
                super_admin=current_user,
                action=f'Student account {action_label}',
                target_type='user',
                target_user=user,
                details=f"Student ID: {student.id}, Reason: {reason_text}",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            AuditLog.log_action(
                actor=current_user,
                action=f'Student account {action_label}',
                target_type='user',
                status=f'{action_label}',
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
        except Exception:
            pass
        db.session.commit()
        return jsonify({'success': True, 'is_active': user.is_active, 'reason': user.lock_reason})
    except CSRFError as e:
        return jsonify({'success': False, 'message': 'CSRF failure'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


################################################ STUDENT #####################################################################

@admin_bp.route('/student_manage')
@login_required
@campus_access_required
def student_manage():
    # Check if the user is a super_admin
    if current_user.role != 'super_admin':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('main.index'))
    
    # Restrict to students within current campus context
    campus_id = getattr(current_user, 'campus_id', None)

    # Build campus-scoped base using explicit subqueries with EXISTS to avoid auto-correlation issues
    # 1) Student.campus_id == campus_id
    # 2) Structured department belongs to campus
    # 3) Legacy free-text department matches a Department in campus
    # 4) Student has inquiries to offices in this campus
    dept_struct_exists = (
        db.session.query(Department.id)
        .filter(and_(Department.id == Student.department_id, Department.campus_id == campus_id))
        .exists()
    )
    dept_name_exists = (
        db.session.query(Department.id)
        .filter(and_(Department.campus_id == campus_id, func.lower(Department.name) == func.lower(Student.department)))
        .exists()
    )
    inquiry_exists = (
        db.session.query(Inquiry.id)
        .join(Office, Inquiry.office_id == Office.id)
        .filter(and_(Inquiry.student_id == Student.id, Office.campus_id == campus_id))
        .exists()
    )

    campus_scope_filter = or_(
        Student.campus_id == campus_id,
        dept_struct_exists,
        dept_name_exists,
        inquiry_exists
    )

    students_base = (
        db.session.query(Student)
        .join(User, User.id == Student.user_id)
        .outerjoin(Department, Department.id == Student.department_id)
        .filter(campus_scope_filter)
    )

    # Filters and search parameters
    q = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or '').strip()  # 'active' | 'inactive' | ''
    dept_id = request.args.get('department_id', type=int)
    year_level = (request.args.get('year_level') or '').strip()
    section = (request.args.get('section') or '').strip()
    email_verified = request.args.get('email_verified')  # 'yes' | 'no' | None
    account_locked = request.args.get('account_locked')  # 'yes' | 'no' | None
    pending_only = request.args.get('pending_only')  # 'yes' | None
    sort = (request.args.get('sort') or 'name').strip()
    order = (request.args.get('order') or 'asc').strip()

    # Apply search
    if q:
        like = f"%{q}%"
        students_base = students_base.filter(
            or_(
                User.first_name.ilike(like),
                func.coalesce(User.middle_name, '').ilike(like),
                User.last_name.ilike(like),
                User.email.ilike(like),
                func.coalesce(Student.student_number, '').ilike(like),
                func.coalesce(Student.department, '').ilike(like),
                func.coalesce(Student.section, '').ilike(like),
                func.coalesce(Student.year_level, '').ilike(like),
                func.coalesce(Department.name, '').ilike(like)
            )
        )

    # Status filters
    if status == 'active':
        students_base = students_base.filter(User.is_active.is_(True))
    elif status == 'inactive':
        students_base = students_base.filter(User.is_active.is_(False))

    if email_verified == 'yes':
        students_base = students_base.filter(User.email_verified.is_(True))
    elif email_verified == 'no':
        students_base = students_base.filter(User.email_verified.is_(False))

    if account_locked == 'yes':
        students_base = students_base.filter(User.account_locked.is_(True))
    elif account_locked == 'no':
        students_base = students_base.filter(User.account_locked.is_(False))

    if dept_id:
        students_base = students_base.filter(Student.department_id == dept_id)
    if year_level:
        students_base = students_base.filter(Student.year_level == year_level)
    if section:
        students_base = students_base.filter(Student.section == section)

    if pending_only == 'yes':
        pending_exists = (
            db.session.query(Inquiry.id)
            .join(Office, Inquiry.office_id == Office.id)
            .filter(and_(Inquiry.student_id == Student.id, Inquiry.status == 'pending', Office.campus_id == campus_id))
            .exists()
        )
        students_base = students_base.filter(pending_exists)

    # Sorting
    sort_columns = {
        'name': (User.last_name, User.first_name),
        'email': (User.email,),
        'student_number': (Student.student_number,),
        'department': (Department.name, Student.department),
        'year_level': (Student.year_level,),
        'section': (Student.section,),
        'created_at': (User.created_at,)
    }
    cols = sort_columns.get(sort, sort_columns['name'])
    ordering = []
    for col in cols:
        ordering.append(col.asc() if order == 'asc' else col.desc())

    students_query = students_base.order_by(*ordering)

    # Pagination params
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # Compute total matching students (distinct IDs due to joins)
    total_students = (students_base.with_entities(func.count(func.distinct(Student.id))).scalar() or 0)

    # Bound page to valid range
    pages = max((total_students + per_page - 1) // per_page, 1)
    if page < 1:
        page = 1
    elif page > pages:
        page = pages

    students = students_query.limit(per_page).offset((page - 1) * per_page).all()
    
    # Stats scoped to campus
    # Active and inactive stats using the same campus-scoped base
    active_students = (db.session.query(func.count(func.distinct(Student.id)))
                       .select_from(Student)
                       .join(User, User.id == Student.user_id)
                       .outerjoin(Department, Department.id == Student.department_id)
                       .filter(campus_scope_filter, User.is_active.is_(True))
                       .scalar() or 0)
    inactive_students = (total_students - active_students) if total_students else 0

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recently_registered = (db.session.query(func.count(func.distinct(Student.id)))
                           .select_from(Student)
                           .join(User, User.id == Student.user_id)
                           .outerjoin(Department, Department.id == Student.department_id)
                           .filter(campus_scope_filter, User.created_at >= seven_days_ago)
                           .scalar() or 0)
    
    # Range for current page
    start_index = 0 if total_students == 0 else (page - 1) * per_page + 1
    end_index = 0 if total_students == 0 else min(page * per_page, total_students)

    # Provide departments for filter UI (campus-specific)
    departments = []
    if campus_id:
        departments = Department.query.filter_by(campus_id=campus_id, is_active=True).order_by(Department.name.asc()).all()

    return render_template('admin/studentmanage.html',
                           students=students,
                           total_students=total_students,
                           active_students=active_students,
                           inactive_students=inactive_students,
                           recently_registered=recently_registered,
                           page=page,
                           pages=pages,
                           per_page=per_page,
                           start_index=start_index,
                           end_index=end_index,
                           # filters state for template
                           q=q,
                           status=status,
                           department_id=dept_id,
                           year_level=year_level,
                           section=section,
                           email_verified=email_verified,
                           account_locked=account_locked,
                           pending_only=pending_only,
                           sort=sort,
                           order=order,
                           departments=departments)


@admin_bp.route('/verify_student_email', methods=['POST'])
@login_required
def verify_student_email():
    """Campus admin bypass: mark a student's email as verified.

    Request JSON: { student_id: int }
    Accept only super_admin; ensure campus scope matches.
    """
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    try:
        data = request.get_json(silent=True) or {}
        student_id = data.get('student_id')
        if not student_id:
            return jsonify({'success': False, 'message': 'Missing student_id'}), 400
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        # Campus scope enforcement
        if getattr(current_user, 'campus_id', None) and student.campus_id != current_user.campus_id:
            return jsonify({'success': False, 'message': 'Campus mismatch'}), 403
        user = student.user
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        # Mark verified (idempotent)
        if not user.email_verified:
            user.mark_email_verified()
            # Audit log
            try:
                SuperAdminActivityLog.log_action(
                    super_admin=current_user,
                    action='Bypassed student email verification',
                    target_type='user',
                    target_user=user,
                    details=f'Student ID: {student.id}',
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                AuditLog.log_action(
                    actor=current_user,
                    action='Bypassed student email verification',
                    target_type='user',
                    status='email_verified',
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
            except Exception:
                pass
            db.session.commit()
        return jsonify({'success': True, 'email_verified': True, 'verified_at': user.email_verified_at.isoformat() if user.email_verified_at else None})
    except CSRFError:
        return jsonify({'success': False, 'message': 'CSRF failure'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/toggle_student_lock', methods=['POST'])
@login_required
def toggle_student_lock():
    if current_user.role != 'super_admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    data = request.json
    student_id = data.get('student_id')
    should_lock = data.get('should_lock')  # True = lock, False = unlock
    reason = data.get('reason', '')  # Optional reason for locking
    
    if student_id is None or should_lock is None:
        return jsonify({'success': False, 'message': 'Missing required data'}), 400
    
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        
        # Get the user associated with the student
        user = student.user
        
        # Toggle account lock status
        if should_lock:
            # Lock the account using the method from User model
            lock_history = user.lock_account(current_user, reason)
            action = 'locked'
        else:
            # Unlock the account using the method from User model
            unlock_history = user.unlock_account(current_user, reason)
            action = 'unlocked'
        
        # Log the super admin action
        SuperAdminActivityLog.log_action(
            super_admin=current_user,
            action=f'Student account {action}',
            target_type='user',
            target_user=user,
            details=f'Student ID: {student.id}, Student Number: {student.student_number}, Reason: {reason}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        # Create an audit log entry
        AuditLog.log_action(
            actor=current_user,
            action=f'Student account {action}',
            target_type='user',
            status=f'Account {action}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        # Return success response with updated status
        return jsonify({
            'success': True, 
            'message': f'Student account has been {action}',
            'account_locked': user.account_locked,
            'lock_reason': user.lock_reason,
            'locked_at': user.locked_at.strftime('%Y-%m-%d %H:%M:%S') if user.locked_at else None
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/view_student/<int:student_id>', methods=['GET', 'POST'])
@login_required
def view_student(student_id):
    if current_user.role != 'super_admin':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('main.index'))
    
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        try:
            student.user.first_name = request.form.get('first_name')
            student.user.middle_name = request.form.get('middle_name')
            student.user.last_name = request.form.get('last_name')
            student.user.email = request.form.get('email')
            
            # Update student-specific fields
            student.student_number = request.form.get('student_number')
            # Structured department assignment
            dept_id = request.form.get('department_id', type=int)
            if dept_id:
                dept = Department.query.filter_by(id=dept_id, campus_id=student.campus_id, is_active=True).first()
                if dept:
                    student.department_id = dept.id
                    student.department = None
            student.year_level = request.form.get('year_level')
            # Sanitize section to single uppercase A–E
            s = request.form.get('section')
            if s:
                import re as _re
                m = _re.search(r'([A-E])', s.strip(), _re.IGNORECASE)
                student.section = m.group(1).upper() if m else None
            else:
                student.section = None
            

            if 'reset_password' in request.form:
 
                new_password = ''.join(random.choices('0123456789', k=4))

                student.user.password_hash = generate_password_hash(new_password)
                
                flash(f'Password has been reset to: {new_password}', 'success')
            
            db.session.commit()
            flash('Student information updated successfully', 'success')
            return redirect(url_for('admin.student_manage'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating student: {str(e)}', 'danger')
    
    # GET or after POST fall-through: provide departments for student's campus
    departments = []
    if student.campus_id:
        departments = Department.query.filter_by(campus_id=student.campus_id, is_active=True).order_by(Department.name.asc()).all()
    return render_template('admin/view_student.html', student=student, departments=departments)
