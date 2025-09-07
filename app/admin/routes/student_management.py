from app.models import Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, OfficeLoginLog, AuditLog, AccountLockHistory, Department
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import func, case, or_
import random
import os
from app.admin import admin_bp
from app.utils.decorators import campus_access_required


################################################ STUDENT #####################################################################

@admin_bp.route('/student_manage')
@login_required
@campus_access_required
def student_manage():
    # Check if the user is a super_admin
    if current_user.role != 'super_admin':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('main.index'))
    
    # Restrict to students that belong to the currently logged-in campus via Student.campus_id
    campus_id = getattr(current_user, 'campus_id', None)
    
    # Base query: students directly assigned to campus
    students_base = (db.session.query(Student)
                     .join(User, User.id == Student.user_id)
                     .filter(Student.campus_id == campus_id))
    
    students = students_base.order_by(User.last_name.asc(), User.first_name.asc()).all()
    
    # Stats scoped to campus
    total_students = (db.session.query(func.count(Student.id))
                      .filter(Student.campus_id == campus_id)
                      .scalar() or 0)
    
    active_students = (db.session.query(func.count(Student.id))
                       .join(User, User.id == Student.user_id)
                       .filter(Student.campus_id == campus_id, User.is_active == True)
                       .scalar() or 0)
    inactive_students = (total_students - active_students) if total_students else 0

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recently_registered = (db.session.query(func.count(Student.id))
                           .join(User, User.id == Student.user_id)
                           .filter(Student.campus_id == campus_id, User.created_at >= seven_days_ago)
                           .scalar() or 0)
    
    return render_template('admin/studentmanage.html',
                           students=students,
                           total_students=total_students,
                           active_students=active_students,
                           inactive_students=inactive_students,
                           recently_registered=recently_registered)

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
            student.section = request.form.get('section')
            

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
