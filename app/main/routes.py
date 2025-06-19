from flask import Blueprint, render_template
from werkzeug.security import generate_password_hash
from app.models import Office, Inquiry, OfficeAdmin

# Replace 'admin' with any password you want to hash
plain_password = "admin"
hashed_password = generate_password_hash(plain_password)

print("Hashed password:", hashed_password)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/offices')
def offices():
    """Display all available offices dynamically from database"""
    # Get all offices from database
    offices = Office.query.all()
    
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
    
    return render_template('offices.html', office_data=office_data)

@main_bp.route('/office/<int:office_id>')
def office_details(office_id):
    """Display detailed information about a specific office"""
    office = Office.query.get_or_404(office_id)
    
    # Get office statistics
    total_inquiries = Inquiry.query.filter_by(office_id=office.id).count()
    pending_inquiries = Inquiry.query.filter_by(office_id=office.id, status='pending').count()
    resolved_inquiries = Inquiry.query.filter_by(office_id=office.id, status='resolved').count()
    
    # Get office admins
    office_admins = [admin for admin in office.office_admins if admin.user.is_active]
    
    # Get supported concern types
    concern_types = [oc.concern_type for oc in office.supported_concerns]
    
    # Check if office is currently available
    is_available = len(office_admins) > 0 and any(admin.user.is_online for admin in office_admins)
    
    # Get recent activity (last 10 inquiries)
    recent_inquiries = Inquiry.query.filter_by(office_id=office.id)\
        .order_by(Inquiry.created_at.desc()).limit(10).all()
    
    return render_template('office_details.html', 
                         office=office,
                         total_inquiries=total_inquiries,
                         pending_inquiries=pending_inquiries,
                         resolved_inquiries=resolved_inquiries,
                         office_admins=office_admins,
                         concern_types=concern_types,
                         is_available=is_available,
                         recent_inquiries=recent_inquiries)

@main_bp.route('/securityprivacy')
def securityprivacy():
    return render_template('securityprivacy.html')

@main_bp.route('/register')
def register():
    return render_template('auth/register.html')