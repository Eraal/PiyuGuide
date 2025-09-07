from app.models import (
    Campus, User, Office, db, OfficeAdmin, SuperSuperAdminActivityLog,
    Student, Inquiry, CounselingSession, Announcement, AuditLog
)
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from app.super_admin import super_admin_bp
from app.utils import role_required

@super_admin_bp.route('/dashboard')
@login_required
@role_required(['super_super_admin'])
def dashboard():
    """Super Super Admin dashboard for managing campuses and super admins"""
    
    # Calculate main statistics
    total_campuses = Campus.query.count()
    active_campuses = Campus.query.filter_by(is_active=True).count()
    inactive_campuses = total_campuses - active_campuses
    
    # Super admin statistics
    total_super_admins = User.query.filter_by(role='super_admin').count()
    active_super_admins = User.query.filter_by(role='super_admin', is_active=True).count()
    unassigned_super_admins = User.query.filter_by(role='super_admin', campus_id=None, is_active=True).count()
    
    # System-wide statistics
    total_offices = Office.query.count()
    total_office_admins = User.query.filter_by(role='office_admin').count()
    total_students = User.query.filter_by(role='student').count()
    active_students = User.query.filter_by(role='student', is_active=True).count()
    
    # Activity statistics (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Inquiries statistics
    total_inquiries = Inquiry.query.count()
    recent_inquiries = Inquiry.query.filter(Inquiry.created_at >= thirty_days_ago).count()
    pending_inquiries = Inquiry.query.filter_by(status='pending').count()
    resolved_inquiries = Inquiry.query.filter_by(status='resolved').count()
    
    # Counseling sessions statistics
    total_sessions = CounselingSession.query.count()
    recent_sessions = CounselingSession.query.filter(CounselingSession.scheduled_at >= thirty_days_ago).count()
    completed_sessions = CounselingSession.query.filter_by(status='completed').count()
    scheduled_sessions = CounselingSession.query.filter_by(status='scheduled').count()
    
    # Announcements statistics
    total_announcements = Announcement.query.count()
    recent_announcements = Announcement.query.filter(Announcement.created_at >= thirty_days_ago).count()
    
    # Recent activity (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_activity = AuditLog.query.filter(
        AuditLog.timestamp >= seven_days_ago
    ).order_by(AuditLog.timestamp.desc()).limit(10).all()
    
    # Get recent campuses
    recent_campuses = Campus.query.order_by(Campus.created_at.desc()).limit(5).all()
    
    # Get campus statistics with detailed counts
    campus_stats = db.session.query(
        Campus,
        func.count(func.distinct(User.id)).label('super_admin_count'),
        func.count(func.distinct(Office.id)).label('office_count')
    ).outerjoin(
        User, and_(Campus.id == User.campus_id, User.role == 'super_admin')
    ).outerjoin(
        Office, Campus.id == Office.campus_id
    ).group_by(Campus.id).order_by(Campus.name).all()
    
    # Get top performing campuses by activity
    # Use DISTINCT counts to avoid overcounting due to multiple one-to-many joins
    top_campuses_by_activity = db.session.query(
        Campus,
        func.count(func.distinct(Inquiry.id)).label('inquiry_count'),
        func.count(func.distinct(CounselingSession.id)).label('session_count')
    ).outerjoin(
        Office, Campus.id == Office.campus_id
    ).outerjoin(
        Inquiry, Office.id == Inquiry.office_id
    ).outerjoin(
        CounselingSession, Office.id == CounselingSession.office_id
    ).group_by(Campus.id).order_by(
        (func.count(func.distinct(Inquiry.id)) + func.count(func.distinct(CounselingSession.id))).desc()
    ).limit(5).all()
    
    # Log this activity
    SuperSuperAdminActivityLog.log_action(
        super_super_admin=current_user,
        action="Viewed Dashboard",
        target_type="system",
        details="Accessed Super Super Admin dashboard",
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    return render_template(
        'super_admin/dashboard.html',
        # Campus statistics
        total_campuses=total_campuses,
        active_campuses=active_campuses,
        inactive_campuses=inactive_campuses,
        
        # Super admin statistics
        total_super_admins=total_super_admins,
        active_super_admins=active_super_admins,
        unassigned_super_admins=unassigned_super_admins,
        
        # System-wide statistics
        total_offices=total_offices,
        total_office_admins=total_office_admins,
        total_students=total_students,
        active_students=active_students,
        
        # Activity statistics
        total_inquiries=total_inquiries,
        recent_inquiries=recent_inquiries,
        pending_inquiries=pending_inquiries,
        resolved_inquiries=resolved_inquiries,
        
        total_sessions=total_sessions,
        recent_sessions=recent_sessions,
        completed_sessions=completed_sessions,
        scheduled_sessions=scheduled_sessions,
        
        total_announcements=total_announcements,
        recent_announcements=recent_announcements,
        
        # Data collections
        recent_activity=recent_activity,
        recent_campuses=recent_campuses,
        campus_stats=campus_stats,
        top_campuses_by_activity=top_campuses_by_activity
    )
