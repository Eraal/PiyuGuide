from flask import Blueprint, render_template, redirect, url_for, flash, session, request, current_app
from werkzeug.security import check_password_hash, generate_password_hash  
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Student, AuditLog, Campus, Department, VerificationToken
from datetime import datetime, timedelta
from app.extensions import db, mail  
from flask_wtf.csrf import CSRFProtect
import secrets, hashlib, hmac


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
            # Block suspended/deactivated accounts before login_user
            if (not user.is_active) or getattr(user, 'account_locked', False):
                reason = user.lock_reason or 'Your account has been suspended.'
                # Audit blocked attempt
                log = AuditLog(
                    actor_id=user.id,
                    actor_role=user.role,
                    action='Suspended account login attempt',
                    target_type='authentication',
                    status_snapshot='blocked',
                    is_success=False,
                    failure_reason=reason,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None
                )
                db.session.add(log)
                db.session.commit()
                return render_template(
                    'auth/login.html',
                    suspended_reason=reason,
                    suppress_flashes=True
                )
            # Update online status and last activity time
            user.is_online = True
            user.last_activity = datetime.utcnow()
            
            # Enforce email verification for students
            if user.role == 'student' and not getattr(user, 'email_verified', False):
                # Optionally auto-resend if last sent is older than 5 minutes
                try:
                    if not user.email_verification_sent_at or (datetime.utcnow() - (user.email_verification_sent_at or datetime.utcnow()) > timedelta(minutes=5)):
                        _issue_and_send_verification(user)
                        db.session.commit()
                except Exception:
                    db.session.rollback()
                # Show verification guidance page
                return redirect(url_for('auth.check_email', email=user.email))

            # Successful login (verified or non-student)
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
        # Sanitize section: only single letter A–E allowed
        section_raw = request.form.get('section')
        section = None
        if section_raw:
            import re as _re
            m = _re.search(r'([A-E])', section_raw.strip(), _re.IGNORECASE)
            section = m.group(1).upper() if m else None
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
            flash('Please use your institutional email (e.g., juan.delacruz@lspu.edu.ph). Personal emails are not accepted.', 'error')
            return redirect(url_for('auth.register'))
        
        # Validate student number format (NNNN-NNNN)
        import re
        if not re.match(r'^\d{4}-\d{4}$', student_number):
            flash('Student number must be in format NNNN-NNNN (e.g., 0222-1756)', 'error')
            return redirect(url_for('auth.register'))
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('This institutional email is already in use. If this is your email, try signing in or reset your password.', 'error')
            return redirect(url_for('auth.register'))
        
        # Check if student number already exists
        existing_student = Student.query.filter_by(student_number=student_number).first()
        if existing_student:
            flash('This student number is already registered. If you believe this is an error, please contact support.', 'error')
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
            is_active=True,
            email_verified=False
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

            # Issue verification email + backup code
            try:
                _issue_and_send_verification(new_user)
            except Exception as send_exc:
                # Log but continue to Check Email page so user can trigger a resend later
                try:
                    current_app.logger.exception("Failed to send verification email right after registration")
                except Exception:
                    pass
                flash('We could not send the verification email right now. You can request a resend on the next page.', 'warning')
            finally:
                # Persist any token records created before the send failed
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Redirect to check-email page (Step 1 of 3)
            return redirect(url_for('auth.check_email', email=new_user.email))
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


# ===================== Email Verification Flow =====================

def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def _issue_and_send_verification(user: User, ttl_hours: int = 48):
    """Create a one-time token + 6-digit code, store hashes, send email via SMTP."""
    # Import lazily to avoid hard dependency errors during linting without installed package
    try:
        from flask_mail import Message
    except Exception:
        Message = None  # type: ignore
    # Try to invalidate old tokens (non-fatal if permissions disallow DELETE in production)
    try:
        VerificationToken.query.filter_by(user_id=user.id, purpose='email_verify', used_at=None).delete()
    except Exception:
        # If this fails (e.g., insufficient privilege), just continue without deletion.
        # We'll issue a new token; lookups always use the most recent when verifying by code.
        try:
            current_app.logger.warning('Could not delete old verification tokens; proceeding with new token')
        except Exception:
            pass
        try:
            db.session.rollback()
        except Exception:
            pass

    # Create a fresh token record
    try:
        raw_token = secrets.token_urlsafe(48)
        token_hash = _hash_value(raw_token)
        # 6-digit numeric code
        code = f"{secrets.randbelow(1000000):06d}"
        code_hash = _hash_value(code)
        vt = VerificationToken(
            user_id=user.id,
            purpose='email_verify',
            token_hash=token_hash,
            code_hash=code_hash,
            attempts=0,
            max_attempts=5,
            expires_at=datetime.utcnow() + timedelta(hours=ttl_hours)
        )
        db.session.add(vt)
        user.email_verification_sent_at = datetime.utcnow()
        db.session.flush()
    except Exception:
        # Ensure session is clean for callers
        db.session.rollback()
        raise

    verify_url = url_for('auth.verify_email', token=raw_token, _external=True)

    # Compose and send email
    subject = 'Verify your email for PiyuGuide'
    recipients = [user.email]
    if Message is None:
        # If Flask-Mail isn't installed, raise a clear error at runtime
        raise RuntimeError('Flask-Mail is required. Install dependencies and set MAIL_* env vars.')
    # Prepare content
    html = None
    body = None
    try:
        html = render_template('email/verify_email.html', user=user, verify_url=verify_url, code=code)
    except Exception:
        body = (
            f"Hello {user.get_full_name()},\n\n"
            f"Please verify your email to activate your account.\n\n"
            f"Click: {verify_url}\n"
            f"Or enter this 6-digit code: {code} (expires in {ttl_hours}h).\n\n"
            f"If you didn’t create an account, you can ignore this email."
        )

    # Send with SMTP first, fallback to Brevo HTTP API if SMTP blocked
    try:
        from app.utils.email_backend import send_email_with_fallback
        send_email_with_fallback(subject=subject, recipients=recipients, html=html, body=body)
    except Exception:
        # Re-raise so the route returns 500 and logs the real error
        raise


@auth_bp.route('/verify-email')
def verify_email():
    token = request.args.get('token', type=str)
    if not token:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('auth.login'))
    token_hash = _hash_value(token)
    vt = VerificationToken.query.filter_by(token_hash=token_hash, purpose='email_verify').first()
    if not vt or vt.is_used or vt.is_expired:
        flash('This verification link is invalid or has expired. You can request a new one below.', 'error')
        return redirect(url_for('auth.check_email'))

    user = User.query.get(vt.user_id)
    if not user:
        flash('Account not found.', 'error')
        return redirect(url_for('auth.login'))

    # Mark verified and consume token
    user.mark_email_verified()
    vt.used_at = datetime.utcnow()
    db.session.commit()

    # Auto-login (Step 3): set campus context and redirect based on role
    try:
        login_user(user)
        # Ensure campus selected for students
        if user.role == 'student' and getattr(user, 'student', None) and user.student.campus_id:
            session['selected_campus_id'] = user.student.campus_id
        flash('Email verified! Welcome.', 'success')
        if user.role == 'student':
            return redirect(url_for('student.dashboard'))
        elif user.role == 'office_admin':
            return redirect(url_for('office.dashboard'))
        elif user.role in ('super_admin', 'super_super_admin'):
            return redirect(url_for('admin.dashboard')) if user.role == 'super_admin' else redirect(url_for('super_admin.dashboard'))
        else:
            return redirect(url_for('auth.login'))
    except Exception:
        return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/code', methods=['GET', 'POST'])
def verify_email_code():
    if request.method == 'GET':
        email = request.args.get('email')
        return render_template('auth/verify_code.html', email=email)

    # POST
    email = request.form.get('email')
    raw_code = request.form.get('code', '') or ''

    # Normalize the entered code to exactly 6 ASCII digits:
    # - Remove spaces, hyphens, and any non-digit characters
    # - Convert any unicode digits (e.g., Arabic-Indic) to ASCII 0-9
    # - Preserve leading zeros
    import unicodedata
    digits = []
    for ch in raw_code:
        # Skip obvious separators and whitespace early
        if ch in {' ', '\u200b', '\u200c', '\u200d', '\u2060', '-', '–', '—', '_'}:
            continue
        if ch.isdigit():
            try:
                d = unicodedata.digit(ch)
            except (TypeError, ValueError):
                # Fallback: if already ASCII digit
                if '0' <= ch <= '9':
                    d = ord(ch) - ord('0')
                else:
                    # Unknown digit-like char; skip
                    continue
            digits.append(str(d))
    code = ''.join(digits)

    if not email or len(code) != 6:
        flash('Invalid code.', 'error')
        return redirect(url_for('auth.verify_email_code', email=email))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('If that email exists, we sent a new code.', 'info')
        return redirect(url_for('auth.login'))
    vt = VerificationToken.query.filter(
        VerificationToken.user_id == user.id,
        VerificationToken.purpose == 'email_verify',
        VerificationToken.used_at.is_(None)
    ).order_by(VerificationToken.created_at.desc()).first()
    if not vt or vt.is_expired:
        flash('Code expired. Please request a new one.', 'warning')
        return redirect(url_for('auth.check_email', email=email))
    # Rate-limit attempts
    if vt.attempts >= (vt.max_attempts or 5):
        flash('Too many attempts. We sent a new verification email.', 'error')
        _issue_and_send_verification(user)
        db.session.commit()
        return redirect(url_for('auth.check_email', email=email))

    vt.attempts += 1
    if hmac.compare_digest(_hash_value(code), vt.code_hash or ''):
        user.mark_email_verified()
        vt.used_at = datetime.utcnow()
        db.session.commit()
        # Auto-login after code verify
        login_user(user)
        if user.role == 'student' and getattr(user, 'student', None) and user.student.campus_id:
            session['selected_campus_id'] = user.student.campus_id
        flash('Email verified! Welcome.', 'success')
        return redirect(url_for('student.dashboard') if user.role == 'student' else url_for('auth.login'))
    else:
        db.session.commit()
        flash('Incorrect code. Please try again.', 'error')
        return redirect(url_for('auth.verify_email_code', email=email))


@auth_bp.route('/verify-email/resend', methods=['POST'])
def resend_verification():
    email = request.form.get('email') or request.args.get('email')
    if not email:
        flash('Email is required.', 'error')
        return redirect(url_for('auth.login'))
    # If a previous error left the transaction in aborted state, clear it first
    try:
        db.session.rollback()
    except Exception:
        pass
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('If that email exists, a verification email was sent.', 'info')
        return redirect(url_for('auth.login'))
    if user.email_verified:
        flash('Your email is already verified. You can log in.', 'info')
        return redirect(url_for('auth.login'))
    # Throttle: 60s between sends
    if user.email_verification_sent_at and (datetime.utcnow() - user.email_verification_sent_at) < timedelta(seconds=60):
        flash('Please wait a minute before requesting again.', 'warning')
        return redirect(url_for('auth.check_email', email=email))
    try:
        _issue_and_send_verification(user)
        db.session.commit()
        flash('Verification email sent. Please check your inbox.', 'success')
    except Exception as send_exc:
        # Log the failure; keep the user on the check page with guidance
        try:
            current_app.logger.exception('Failed to resend verification email')
        except Exception:
            pass
        # Ensure DB state is consistent (token may already have been created)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        flash('We could not send the verification email right now. Please try again later.', 'warning')
    return redirect(url_for('auth.check_email', email=email))


@auth_bp.route('/check-email')
def check_email():
    email = request.args.get('email')
    return render_template('auth/check_email.html', email=email)