from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user
import datetime

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

def format_date(timestamp):
    """
    Format a datetime object for display in frontend
    :param timestamp: datetime object
    :return: formatted date string
    """
    if not timestamp:
        return "N/A"
        
    # Check if it's already a string
    if isinstance(timestamp, str):
        return timestamp
        
    now = datetime.datetime.utcnow()
    diff = now - timestamp
    
    if diff.days == 0:
        # Same day formatting (show time)
        return timestamp.strftime('%I:%M %p')
    elif diff.days < 7:
        # Within the week (show day and time)
        return timestamp.strftime('%a, %I:%M %p')
    else:
        # Older messages (show full date)
        return timestamp.strftime('%b %d, %Y %I:%M %p')