from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from flask_login import current_user
from app.models import Office, Inquiry, OfficeAdmin, Campus

# Replace 'admin' with any password you want to hash
plain_password = "admin"
hashed_password = generate_password_hash(plain_password)

print("Hashed password:", hashed_password)

main_bp = Blueprint('main', __name__)

def validate_campus_access(campus_id):
    """
    Validate if current user can access the specified campus.
    For super_admin users, they can only access their assigned campus.
    For other users, no restrictions.
    """
    if not current_user.is_authenticated:
        return True  # Non-authenticated users can browse campuses
    
    if current_user.role == 'super_admin':
        # Super admins can only access their assigned campus
        if not current_user.campus_id:
            return False  # No campus assigned
        return current_user.campus_id == campus_id
    
    # Other roles have no campus restrictions
    return True

@main_bp.route('/')
def index():
    """Root route - redirect to campus selection"""
    return redirect(url_for('main.campus_selection'))

@main_bp.route('/offices')
def offices():
    """Display all available offices - redirect to campus-specific if campus is selected"""
    # Check if there's a selected campus in session
    selected_campus_id = session.get('selected_campus_id')
    if selected_campus_id:
        # Redirect to campus-specific offices page
        return redirect(url_for('main.campus_offices', campus_id=selected_campus_id))
    
    # If no campus selected, redirect to campus selection
    return redirect(url_for('main.campus_selection'))

@main_bp.route('/office/<int:office_id>')
def office_details(office_id):
    """Display detailed information about a specific office - redirect to campus-specific if campus is selected"""
    office = Office.query.get_or_404(office_id)
    
    # Check if there's a selected campus in session
    selected_campus_id = session.get('selected_campus_id')
    if selected_campus_id and office.campus_id == selected_campus_id:
        # Redirect to campus-specific office details
        return redirect(url_for('main.campus_office_details', campus_id=selected_campus_id, office_id=office_id))
    elif office.campus_id:
        # Redirect to campus-specific office details with the office's campus
        return redirect(url_for('main.campus_office_details', campus_id=office.campus_id, office_id=office_id))
    
    # Fallback - redirect to campus selection
    return redirect(url_for('main.campus_selection'))

@main_bp.route('/securityprivacy')
def securityprivacy():
    """Security & Privacy page - redirect to campus-specific if campus is selected"""
    # Check if there's a selected campus in session
    selected_campus_id = session.get('selected_campus_id')
    if selected_campus_id:
        # Use the campus-specific template
        campus = Campus.query.get(selected_campus_id)
        return render_template('campus/securityprivacy.html', campus=campus)
    
    # If no campus selected, redirect to campus selection
    return redirect(url_for('main.campus_selection'))

@main_bp.route('/register')
def register():
    selected_campus_id = session.get('selected_campus_id')
    if selected_campus_id:
        return redirect(url_for('auth.register', campus_id=selected_campus_id))
    return redirect(url_for('auth.register'))

@main_bp.route('/campus')
@main_bp.route('/campus/<int:campus_id>')
def campus_landing(campus_id=None):
    """Campus landing page - dynamically show campus information"""
    
    # If campus_id is provided, use that campus
    if campus_id:
        # Validate campus access for super_admin users
        if not validate_campus_access(campus_id):
            flash('You do not have permission to access this campus.', 'error')
            if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
                return redirect(url_for('main.campus_landing', campus_id=current_user.campus_id))
            return redirect(url_for('main.campus_selection'))
        
        campus = Campus.query.get_or_404(campus_id)
        
        # Additional check: If user is a super_admin, ensure they can only access their assigned campus
        if current_user.is_authenticated and current_user.role == 'super_admin':
            if current_user.campus_id != campus_id:
                flash('Access denied. You can only access your assigned campus.', 'error')
                return redirect(url_for('main.campus_landing', campus_id=current_user.campus_id))
        # Persist selected campus
        session['selected_campus_id'] = campus_id
    else:
        # Check if there's a selected campus in session
        selected_campus_id = session.get('selected_campus_id')
        if selected_campus_id:
            # Validate access to the session campus
            if not validate_campus_access(selected_campus_id):
                # Clear invalid session campus
                session.pop('selected_campus_id', None)
                if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
                    return redirect(url_for('main.campus_landing', campus_id=current_user.campus_id))
                return redirect(url_for('main.campus_selection'))
            
            campus = Campus.query.get(selected_campus_id)
        else:
            # For super_admin, redirect to their assigned campus
            if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
                return redirect(url_for('main.campus_landing', campus_id=current_user.campus_id))
            
            # Get the first active campus as default
            campus = Campus.query.filter_by(is_active=True).first()
            if campus:
                session['selected_campus_id'] = campus.id
    
    if not campus:
        flash('No campus found. Please contact the administrator.', 'error')
        return redirect(url_for('main.index'))
    
    # Get campus statistics
    total_offices = Office.query.filter_by(campus_id=campus.id).count()
    active_offices = Office.query.filter_by(campus_id=campus.id).filter(
        Office.office_admins.any()
    ).count()
    
    # Get offices for this campus
    offices = Office.query.filter_by(campus_id=campus.id).all()
    
    # Ensure campus selection persists in session for auth flow
    session['selected_campus_id'] = campus.id
    return render_template('campus/index.html',
                         campus=campus,
                         total_offices=total_offices,
                         active_offices=active_offices,
                         offices=offices)

@main_bp.route('/campus/<int:campus_id>/offices')
def campus_offices(campus_id):
    """Display offices for a specific campus"""
    # Validate campus access for super_admin users
    if not validate_campus_access(campus_id):
        flash('You do not have permission to access this campus.', 'error')
        if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
            return redirect(url_for('main.campus_offices', campus_id=current_user.campus_id))
        return redirect(url_for('main.campus_selection'))
    
    campus = Campus.query.get_or_404(campus_id)
    session['selected_campus_id'] = campus_id
    
    # Get all offices for this campus
    offices = Office.query.filter_by(campus_id=campus_id).all()
    
    # Get office statistics for each office
    office_data = []
    for office in offices:
        # Count total inquiries for this office
        total_inquiries = Inquiry.query.filter_by(office_id=office.id).count()
        
        # Count pending inquiries
        pending_inquiries = Inquiry.query.filter_by(office_id=office.id, status='pending').count()
        
        # Check if office has active admins
        has_active_admins = any(admin.user.is_active for admin in office.office_admins)
        
        # Get supported concern types
        concern_types = [oc.concern_type for oc in office.supported_concerns]
        
        office_data.append({
            'office': office,
            'total_inquiries': total_inquiries,
            'pending_inquiries': pending_inquiries,
            'has_active_admins': has_active_admins,
            'concern_types': concern_types,
            'is_available': has_active_admins and len(office.office_admins) > 0
        })
    
    return render_template('campus/offices.html', 
                         campus=campus,
                         office_data=office_data)

@main_bp.route('/campus/<int:campus_id>/office/<int:office_id>')
def campus_office_details(campus_id, office_id):
    """Display office details for a specific campus"""
    # Validate campus access for super_admin users
    if not validate_campus_access(campus_id):
        flash('You do not have permission to access this campus.', 'error')
        if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
            return redirect(url_for('main.campus_office_details', campus_id=current_user.campus_id, office_id=office_id))
        return redirect(url_for('main.campus_selection'))
    
    campus = Campus.query.get_or_404(campus_id)
    office = Office.query.filter_by(id=office_id, campus_id=campus_id).first_or_404()
    session['selected_campus_id'] = campus_id
    
    # Get office statistics
    total_inquiries = Inquiry.query.filter_by(office_id=office.id).count()
    pending_inquiries = Inquiry.query.filter_by(office_id=office.id, status='pending').count()
    resolved_inquiries = Inquiry.query.filter_by(office_id=office.id, status='resolved').count()
    
    # Get office admins
    office_admins = [admin.user for admin in office.office_admins if admin.user.is_active]
    
    # Get supported concern types
    concern_types = [oc.concern_type for oc in office.supported_concerns]
    
    # Check if office is available (has active admins)
    is_available = len(office_admins) > 0
    
    # Get recent inquiries
    recent_inquiries = Inquiry.query.filter_by(office_id=office.id) \
        .order_by(Inquiry.created_at.desc()).limit(10).all()
    
    return render_template('campus/office_details.html',
                         campus=campus,
                         office=office,
                         total_inquiries=total_inquiries,
                         pending_inquiries=pending_inquiries,
                         resolved_inquiries=resolved_inquiries,
                         office_admins=office_admins,
                         concern_types=concern_types,
                         is_available=is_available,
                         recent_inquiries=recent_inquiries)

@main_bp.route('/campus/<int:campus_id>/securityprivacy')
def campus_securityprivacy(campus_id):
    """Security & Privacy page for a specific campus"""
    # Validate campus access for super_admin users
    if not validate_campus_access(campus_id):
        flash('You do not have permission to access this campus.', 'error')
        if current_user.is_authenticated and current_user.role == 'super_admin' and current_user.campus_id:
            return redirect(url_for('main.campus_securityprivacy', campus_id=current_user.campus_id))
        return redirect(url_for('main.campus_selection'))
    
    campus = Campus.query.get_or_404(campus_id)
    session['selected_campus_id'] = campus_id
    return render_template('campus/securityprivacy.html', campus=campus)

@main_bp.route('/campus-selection')
def campus_selection():
    """Display available campuses for selection"""
    # If a super_admin is already logged in, redirect them to their assigned campus
    if current_user.is_authenticated and current_user.role == 'super_admin':
        if current_user.campus_id:
            flash('You are already assigned to a specific campus.', 'info')
            return redirect(url_for('main.campus_landing', campus_id=current_user.campus_id))
        else:
            flash('Your account is not assigned to any campus. Please contact the system administrator.', 'error')
            return redirect(url_for('auth.logout'))
    
    campuses = Campus.query.filter_by(is_active=True).all()
    return render_template('campus_selection.html', campuses=campuses)