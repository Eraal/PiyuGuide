from flask import Blueprint

student_bp = Blueprint('student', __name__, url_prefix='/student')

# Import routes after Blueprint definition to avoid circular imports
from .routes import dashboard, inquiries, counseling, announcements, notifications, university_offices