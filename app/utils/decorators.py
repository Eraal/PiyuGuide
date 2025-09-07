from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user

def role_required(roles):
    """
    Decorator for routes that should be accessible only by users with specific roles
    :param roles: List of allowed roles (e.g. ['super_admin', 'office_admin'])
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Debug information
            print(f"Current user authenticated: {current_user.is_authenticated}")
            if current_user.is_authenticated:
                print(f"Current user role: {current_user.role}")
                print(f"Required roles: {roles}")
            
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Check if user has the required role
            if current_user.role not in roles:
                flash(f'You need {", ".join(roles)} role to access this page. Your role: {current_user.role}', 'danger')
                return redirect(url_for('main.index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def campus_access_required(f):
    """
    Decorator for routes that should validate campus access for super_admin users
    Super admin users can only access data from their assigned campus
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, request
        
        # Check if user is authenticated
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Only validate campus access for super_admin users
        if current_user.role == 'super_admin':
            # Check if super_admin has an assigned campus
            if not current_user.campus_id:
                flash('Your account is not assigned to any campus. Please contact the system administrator.', 'error')
                return redirect(url_for('auth.login'))
            
            # Validate session campus first - it should ALWAYS match the user's assigned campus
            session_campus_id = session.get('selected_campus_id')
            if session_campus_id and session_campus_id != current_user.campus_id:
                flash('Access denied. You can only access your assigned campus.', 'error')
                # Force set session to user's assigned campus
                session['selected_campus_id'] = current_user.campus_id
                return redirect(url_for('admin.dashboard'))
            
            # Set the session campus to the user's assigned campus if not set
            if not session_campus_id:
                session['selected_campus_id'] = current_user.campus_id
            
            # If there's a campus_id in the route parameters, validate it strictly
            campus_id_from_route = kwargs.get('campus_id') or request.args.get('campus_id')
            if campus_id_from_route:
                try:
                    campus_id_from_route = int(campus_id_from_route)
                    if campus_id_from_route != current_user.campus_id:
                        flash('Access denied. You can only access your assigned campus.', 'error')
                        return redirect(url_for('admin.dashboard'))
                except (ValueError, TypeError):
                    flash('Invalid campus ID.', 'error')
                    return redirect(url_for('admin.dashboard'))
            
            # Additional validation: Ensure any office_id parameters correspond to offices in the user's campus
            office_id_from_route = kwargs.get('office_id') or request.args.get('office_id')
            if office_id_from_route:
                try:
                    office_id_from_route = int(office_id_from_route)
                    from app.models import Office
                    office = Office.query.get(office_id_from_route)
                    if office and office.campus_id != current_user.campus_id:
                        flash('Access denied. You can only access offices in your assigned campus.', 'error')
                        return redirect(url_for('admin.dashboard'))
                except (ValueError, TypeError):
                    flash('Invalid office ID.', 'error')
                    return redirect(url_for('admin.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """
    Decorator for routes that should be accessible only by student users
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Check if user has the student role
        if current_user.role != 'student':
            flash('You need to be a student to access this page.', 'danger')
            return redirect(url_for('main.index'))
            
        return f(*args, **kwargs)
    return decorated_function
