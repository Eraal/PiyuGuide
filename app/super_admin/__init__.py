from flask import Blueprint

super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/super-admin')

# Import routes after blueprint creation to avoid circular imports
from app.super_admin.routes import campus_management, super_admin_management, dashboard, settings, auth
