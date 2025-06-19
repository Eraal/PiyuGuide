from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import time 
from sqlalchemy import func, case, desc, or_ 
from app.office import office_bp
from app.utils import role_required


@office_bp.route('/office-activity-logs')
@login_required
@role_required(['office_admin'])
def office_activity_logs():
    pass