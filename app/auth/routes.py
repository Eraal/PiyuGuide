from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from werkzeug.security import check_password_hash, generate_password_hash  
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Student, AuditLog, Campus, Department
from datetime import datetime
from app.extensions import db  
from flask_wtf.csrf import CSRFProtect


auth_bp = Blueprint('auth', __name__, template_folder='../templates') 


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If a campus_id is provided (e.g., from campus pages), persist it for context
    campus_id = request.args.get('campus_id', type=int)
    if campus_id:
        from app.models import Campus
        campus = Campus.query.get(campus_id)
        if campus:
            session['selected_campus_id'] = campus.id
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Update online status and last activity time
            user.is_online = True
            user.last_activity = datetime.utcnow()
            
            # Successful login
            login_user(user)
            flash('Login successful!', 'success')

            # Log successful login
            log = AuditLog(
                actor_id=user.id,
                actor_role=user.role,
                action='Logged in',
                target_type='authentication',
                status_snapshot='success',
                is_success=True,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None
            )
            db.session.add(log)
            
            # If user is an office admin, create an office login log
            if user.role == 'office_admin' and user.office_admin:
                from app.models import OfficeLoginLog
                login_log = OfficeLoginLog.log_login(
                    office_admin=user.office_admin,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None
                )
            
            db.session.commit()
            
            # Redirect based on role
            if user.role == 'super_super_admin':
                return redirect(url_for('super_admin.dashboard'))
            elif user.role == 'super_admin':
                # Validate campus assignment for super_admin
                if not user.campus_id:
                    flash('Your account is not assigned to any campus. Please contact the system administrator.', 'error')
                    logout_user()
                    return redirect(url_for('auth.login'))
                
                # Check if there's a different campus in session than the one assigned to this super admin
                session_campus_id = session.get('selected_campus_id')
                if session_campus_id and session_campus_id != user.campus_id:
                    flash('You can only access your assigned campus. Redirecting you to the correct campus.', 'warning')
                    # Clear the invalid campus from session
                    session.pop('selected_campus_id', None)
                
                # Set the campus in session for consistent access
                session['selected_campus_id'] = user.campus_id
                return redirect(url_for('admin.dashboard')) 
            elif user.role == 'office_admin':
                return redirect(url_for('office.dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student.dashboard'))
            else:
                # Unknown role – present error modal on the login page without reloading again
                return render_template(
                    'auth/login.html',
                    login_error_message='Unknown user role. Please contact the administrator.',
                    suppress_flashes=True
                )
        else:
            # Failed login attempt
            log = AuditLog(
                actor_id=user.id if user else None,
                actor_role=user.role if user else None,
                action='Failed login attempt',
                target_type='authentication',
                status_snapshot='failed',
                is_success=False,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                failure_reason='Invalid credentials'
            )
            db.session.add(log)
            db.session.commit()
            # Render login with inline error modal, no extra redirect
            return render_template(
                'auth/login.html',
                login_error_message='Invalid email or password. Please try again.',
                suppress_flashes=True
            )
    
    return render_template('auth/login.html')



@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Ensure campus context is present (non-authenticated flow requires campus selection first)
    campus_id = session.get('selected_campus_id') or request.args.get('campus_id', type=int)
    if request.method == 'POST':
        # Get form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Get student-specific fields
        student_number = request.form.get('student_number')
        # Legacy field replaced by structured department
        department_id = request.form.get('department_id', type=int)
        year_level = request.form.get('year_level')
        section = request.form.get('section')
        # Campus selection from form should take priority if provided
        campus_id_from_form = request.form.get('campus_id', type=int)
        if campus_id_from_form:
            campus_id = campus_id_from_form
        
        if not first_name or not last_name or not email or not password:
            flash('All fields are required', 'error')
            return redirect(url_for('auth.register'))
        
        if not student_number or not department_id or not year_level or not section:
            flash('Student number, department, year level, and section are required', 'error')
            return redirect(url_for('auth.register'))
        
        if not email.endswith('@lspu.edu.ph'):
            flash('Registration is only allowed for LSPU students with @lspu.edu.ph email address', 'error')
            return redirect(url_for('auth.register'))
        
        # Validate student number format (NNNN-NNNN)
        import re
        if not re.match(r'^\d{4}-\d{4}$', student_number):
            flash('Student number must be in format NNNN-NNNN (e.g., 0222-1756)', 'error')
            return redirect(url_for('auth.register'))
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists', 'error')
            return redirect(url_for('auth.register'))
        
        # Check if student number already exists
        existing_student = Student.query.filter_by(student_number=student_number).first()
        if existing_student:
            flash('Student number already exists', 'error')
            return redirect(url_for('auth.register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('auth.register'))
        
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            role='student',  
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            is_active=True
        )
        
        try:
            db.session.add(new_user)
            db.session.flush()  
            
            # Determine campus to assign
            if not campus_id:
                # As a guard, require campus selection for correct flow
                db.session.rollback()
                flash('Please select a campus before registering.', 'error')
                return redirect(url_for('main.campus_selection'))
            # Validate campus exists
            campus = Campus.query.get(campus_id)
            if not campus:
                db.session.rollback()
                flash('Selected campus not found.', 'error')
                return redirect(url_for('main.campus_selection'))
            # Persist campus in session
            session['selected_campus_id'] = campus.id

            # Validate department belongs to selected campus and is active
            dept = Department.query.filter_by(id=department_id, campus_id=campus.id, is_active=True).first()
            if not dept:
                db.session.rollback()
                flash('Selected department is invalid for this campus.', 'error')
                return redirect(url_for('auth.register', campus_id=campus.id))

            student = Student(
                user_id=new_user.id,
                student_number=student_number,
                department=dept.name,  # keep legacy text for compatibility
                department_id=dept.id,
                year_level=year_level,
                section=section,
                campus_id=campus.id
            )
            db.session.add(student)
            
            db.session.commit()
            flash('Registration successful! You can now log in', 'success')
            # Redirect back to campus-specific login
            return redirect(url_for('auth.login', campus_id=campus.id))
        except Exception as e:
            db.session.rollback()
            print(f"Error during registration: {e}")  
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('auth.register'))
    
    # GET - if campus provided in query, set it in session for template context
    if campus_id:
        session['selected_campus_id'] = campus_id
    # Provide campuses list for selection in the form
    campuses = Campus.query.filter_by(is_active=True).all()
    selected_campus_id = campus_id
    # Departments: if campus preselected, fetch that campus' active departments
    departments = []
    if selected_campus_id:
        departments = Department.query.filter_by(campus_id=selected_campus_id, is_active=True).order_by(Department.name.asc()).all()
    return render_template('auth/register.html', campuses=campuses, selected_campus_id=selected_campus_id, departments=departments)




@auth_bp.route('/logout')
@login_required 
def logout():
    # Update online status and last activity before logging out
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_activity = datetime.utcnow()

        log = AuditLog(
            actor_id=current_user.id,
            actor_role=current_user.role,
            action='Logged out',
            target_type='authentication',
            status_snapshot='success',
            is_success=True,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )

        # If user is an office admin, update their office login log
        if current_user.role == 'office_admin' and current_user.office_admin:
            from app.models import OfficeLoginLog
            # Find the most recent login log for this admin that doesn't have a logout time
            login_log = OfficeLoginLog.query.filter_by(
                office_admin_id=current_user.office_admin.id,
                logout_time=None
            ).order_by(OfficeLoginLog.login_time.desc()).first()

            if login_log:
                login_log.update_logout()

        db.session.add(log)
        db.session.commit()

    # Perform the actual logout
    logout_user()

    # Always clear campus context and go to campus selection
    session.pop('selected_campus_id', None)

    flash('You have been logged out.', 'success')
    return redirect(url_for('main.campus_selection'))