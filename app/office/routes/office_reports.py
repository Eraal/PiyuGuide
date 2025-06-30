from app.models import (
    Inquiry, InquiryMessage, User, Office, db, OfficeAdmin, 
    Student, CounselingSession, StudentActivityLog, SuperAdminActivityLog, 
    OfficeLoginLog, AuditLog, Announcement, ConcernType, OfficeConcernType
)
from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, case, desc, or_, and_
from app.office import office_bp
import io
import csv
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.units import inch
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


@office_bp.route('/reports')
@login_required
def office_reports():
    """Main reports dashboard page"""
    office_id = current_user.office_admin.office_id
    
    # Get report statistics
    stats = get_report_stats(office_id)
    
    # Get concern types that are supported by this office only
    concern_types = db.session.query(ConcernType)\
        .join(OfficeConcernType)\
        .filter(OfficeConcernType.office_id == office_id)\
        .all()
    
    return render_template('office/office_reports.html', 
                         stats=stats, 
                         concern_types=concern_types)


@office_bp.route('/reports/generate', methods=['POST'])
@login_required
def generate_report():
    """Generate and download reports based on user selection"""
    office_id = current_user.office_admin.office_id
    
    data = request.get_json()
    
    # Debug logging
    print(f"Received data: {data}")
    
    if not data:
        return jsonify({'error': 'No data received'}), 400
    
    report_type = data.get('report_type')
    date_range = data.get('date_range')
    format_type = data.get('format')
    filters = data.get('filters', {})
    
    # Validation
    if not report_type:
        return jsonify({'error': 'Report type is required'}), 400
    
    if not date_range:
        return jsonify({'error': 'Date range is required'}), 400
        
    if not format_type:
        return jsonify({'error': 'Export format is required'}), 400
    
    print(f"Report type: {report_type}, Date range: {date_range}, Format: {format_type}")
    
    # Parse date range
    start_date, end_date = parse_date_range(date_range)
    
    try:
        if report_type == 'inquiries':
            return generate_inquiries_report(office_id, start_date, end_date, format_type, filters)
        elif report_type == 'counseling':
            return generate_counseling_report(office_id, start_date, end_date, format_type, filters)
        elif report_type == 'activity':
            return generate_activity_report(office_id, start_date, end_date, format_type, filters)
        elif report_type == 'summary':
            return generate_summary_report(office_id, start_date, end_date, format_type, filters)
        else:
            return jsonify({'error': f'Invalid report type: {report_type}'}), 400
            
    except Exception as e:
        import traceback
        print(f"Error generating report: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


def get_report_stats(office_id):
    """Get statistics for the reports dashboard"""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    
    # Total inquiries
    total_inquiries = Inquiry.query.filter_by(office_id=office_id).count()
    
    # Inquiries this month
    inquiries_this_month = Inquiry.query.filter(
        Inquiry.office_id == office_id,
        Inquiry.created_at >= thirty_days_ago
    ).count()
    
    # Total counseling sessions
    total_sessions = CounselingSession.query.filter_by(office_id=office_id).count()
    
    # Sessions this month
    sessions_this_month = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= thirty_days_ago
    ).count()
    
    # Response rate calculation
    responded_inquiries = Inquiry.query.filter(
        Inquiry.office_id == office_id,
        Inquiry.status.in_(['resolved', 'in_progress'])
    ).count()
    
    response_rate = (responded_inquiries / total_inquiries * 100) if total_inquiries > 0 else 0
    
    # Average resolution time (simplified)
    avg_resolution_time = "2.5 days"  # This would need proper calculation
    
    return {
        'total_inquiries': total_inquiries,
        'inquiries_this_month': inquiries_this_month,
        'total_sessions': total_sessions,
        'sessions_this_month': sessions_this_month,
        'response_rate': round(response_rate, 1),
        'avg_resolution_time': avg_resolution_time
    }


def parse_date_range(date_range):
    """Parse date range string into start and end dates"""
    now = datetime.utcnow()
    
    if date_range == 'last_7_days':
        start_date = now - timedelta(days=7)
        end_date = now
    elif date_range == 'last_30_days':
        start_date = now - timedelta(days=30)
        end_date = now
    elif date_range == 'last_90_days':
        start_date = now - timedelta(days=90)
        end_date = now
    elif date_range == 'current_month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif date_range == 'current_year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    else:
        # Default to last 30 days
        start_date = now - timedelta(days=30)
        end_date = now
    
    return start_date, end_date


def generate_inquiries_report(office_id, start_date, end_date, format_type, filters):
    """Generate inquiries report"""
    # Build query
    query = Inquiry.query.filter(
        Inquiry.office_id == office_id,
        Inquiry.created_at >= start_date,
        Inquiry.created_at <= end_date
    )
    
    # Apply filters
    if filters.get('status'):
        query = query.filter(Inquiry.status == filters['status'])
    
    if filters.get('concern_type'):
        query = query.join(Inquiry.concerns).filter(
            Inquiry.concerns.any(concern_type_id=filters['concern_type'])
        )
    
    inquiries = query.order_by(desc(Inquiry.created_at)).all()
    
    if format_type == 'csv':
        return generate_csv_response(inquiries, 'inquiries')
    elif format_type == 'excel':
        return generate_excel_response(inquiries, 'inquiries')
    elif format_type == 'pdf':
        return generate_pdf_response(inquiries, 'inquiries')
    
    return jsonify({'error': 'Invalid format type'}), 400


def generate_counseling_report(office_id, start_date, end_date, format_type, filters):
    """Generate counseling sessions report"""
    query = CounselingSession.query.filter(
        CounselingSession.office_id == office_id,
        CounselingSession.scheduled_at >= start_date,
        CounselingSession.scheduled_at <= end_date
    )
    
    # Apply filters
    if filters.get('status'):
        query = query.filter(CounselingSession.status == filters['status'])
    
    sessions = query.order_by(desc(CounselingSession.scheduled_at)).all()
    
    if format_type == 'csv':
        return generate_csv_response(sessions, 'counseling')
    elif format_type == 'excel':
        return generate_excel_response(sessions, 'counseling')
    elif format_type == 'pdf':
        return generate_pdf_response(sessions, 'counseling')
    
    return jsonify({'error': 'Invalid format type'}), 400


def generate_activity_report(office_id, start_date, end_date, format_type, filters):
    """Generate activity logs report"""
    # This would query activity logs if available
    # For now, return empty data
    return jsonify({'message': 'Activity report generation not yet implemented'}), 501


def generate_summary_report(office_id, start_date, end_date, format_type, filters):
    """Generate summary report with statistics"""
    stats = get_detailed_stats(office_id, start_date, end_date)
    
    if format_type == 'pdf':
        return generate_summary_pdf(stats)
    elif format_type == 'excel':
        return generate_summary_excel(stats)
    
    return jsonify({'error': 'Invalid format type for summary report'}), 400


def get_detailed_stats(office_id, start_date, end_date):
    """Get detailed statistics for the given period"""
    # Implementation would include detailed statistics
    # For now, return basic stats
    return get_report_stats(office_id)


def generate_csv_response(data, report_type):
    """Generate CSV response"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type == 'inquiries':
        # Write CSV headers
        writer.writerow(['ID', 'Subject', 'Student Name', 'Student Email', 'Status', 'Created Date', 'Concerns'])
        
        # Write data rows
        for inquiry in data:
            concerns = ', '.join([concern.concern_type.name for concern in inquiry.concerns])
            writer.writerow([
                inquiry.id,
                inquiry.subject,
                inquiry.student.user.get_full_name(),
                inquiry.student.user.email,
                inquiry.status,
                inquiry.created_at.strftime('%Y-%m-%d %H:%M'),
                concerns
            ])
    
    elif report_type == 'counseling':
        writer.writerow(['ID', 'Student Name', 'Student Email', 'Status', 'Scheduled Date', 'Duration', 'Type'])
        
        for session in data:
            writer.writerow([
                session.id,
                session.student.user.get_full_name(),
                session.student.user.email,
                session.status,
                session.scheduled_at.strftime('%Y-%m-%d %H:%M') if session.scheduled_at else '',
                f"{session.duration_minutes} minutes" if session.duration_minutes else '',
                'Video' if session.is_video_session else 'In-person'
            ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={report_type}_report.csv'}
    )


def generate_excel_response(data, report_type):
    """Generate Excel response"""
    output = io.BytesIO()
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = f"{report_type.title()} Report"
    
    # Styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    if report_type == 'inquiries':
        # Headers
        headers = ['ID', 'Subject', 'Student Name', 'Student Email', 'Status', 'Created Date', 'Concerns']
        for col, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
        
        # Data
        for row, inquiry in enumerate(data, 2):
            concerns = ', '.join([concern.concern_type.name for concern in inquiry.concerns])
            row_data = [
                inquiry.id,
                inquiry.subject,
                inquiry.student.user.get_full_name(),
                inquiry.student.user.email,
                inquiry.status,
                inquiry.created_at.strftime('%Y-%m-%d %H:%M'),
                concerns
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = worksheet.cell(row=row, column=col, value=value)
                cell.border = border
    
    elif report_type == 'counseling':
        headers = ['ID', 'Student Name', 'Student Email', 'Status', 'Scheduled Date', 'Duration', 'Type']
        for col, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
        
        for row, session in enumerate(data, 2):
            row_data = [
                session.id,
                session.student.user.get_full_name(),
                session.student.user.email,
                session.status,
                session.scheduled_at.strftime('%Y-%m-%d %H:%M') if session.scheduled_at else '',
                f"{session.duration_minutes} minutes" if session.duration_minutes else '',
                'Video' if session.is_video_session else 'In-person'
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = worksheet.cell(row=row, column=col, value=value)
                cell.border = border
    
    # Auto-adjust column widths
    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        worksheet.column_dimensions[column_letter].width = adjusted_width
    
    workbook.save(output)
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={report_type}_report.xlsx'}
    )


def generate_pdf_response(data, report_type):
    """Generate PDF response with enhanced styling"""
    output = io.BytesIO()
    
    # Custom page template with margins
    doc = SimpleDocTemplate(
        output, 
        pagesize=A4,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch
    )
    story = []
    
    # Enhanced Styles
    styles = getSampleStyleSheet()
    
    # Header style with gradient-like effect
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Normal'],
        fontSize=24,
        textColor=colors.HexColor('#1a365d'),
        fontName='Helvetica-Bold',
        alignment=1,  # Center
        spaceAfter=10
    )
    
    # Subtitle style
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#4a5568'),
        fontName='Helvetica',
        alignment=1,  # Center
        spaceAfter=30
    )
    
    # Section header style
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2d3748'),
        fontName='Helvetica-Bold',
        spaceBefore=20,
        spaceAfter=10
    )
    
    # Add header with branding
    story.append(Paragraph("📊 KapiyuGuide Reports", header_style))
    
    # Current date and report type
    current_date = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    story.append(Paragraph(f"{report_type.title()} Report - Generated on {current_date}", subtitle_style))
    
    # Add a decorative line
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#4299e1')))
    story.append(Spacer(1, 20))
    
    if report_type == 'inquiries':
        # Summary section for inquiries
        story.append(Paragraph("📋 Inquiry Summary", section_style))
        
        summary_data = [
            ['Total Inquiries:', str(len(data))],
            ['Report Period:', f"Various dates (Last {len(data)} inquiries)"],
            ['Status Breakdown:', get_status_breakdown_text(data)]
        ]
        
        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # Main data section
        story.append(Paragraph("📝 Detailed Inquiry List", section_style))
        
        # Enhanced table data with better formatting
        table_data = [['ID', 'Subject', 'Student', 'Status', 'Date', 'Concerns']]
        
        for inquiry in data:
            concerns = ', '.join([concern.concern_type.name for concern in inquiry.concerns])
            # Better text wrapping and formatting
            subject_text = inquiry.subject[:35] + '...' if len(inquiry.subject) > 35 else inquiry.subject
            concerns_text = concerns[:40] + '...' if len(concerns) > 40 else concerns
            
            # Status formatting with color coding
            status_text = inquiry.status.replace('_', ' ').title()
            
            table_data.append([
                str(inquiry.id),
                subject_text,
                inquiry.student.user.get_full_name(),
                status_text,
                inquiry.created_at.strftime('%m/%d/%Y'),
                concerns_text
            ])
    
    elif report_type == 'counseling':
        # Summary section for counseling
        story.append(Paragraph("🎯 Counseling Session Summary", section_style))
        
        video_count = len([s for s in data if s.is_video_session])
        in_person_count = len(data) - video_count
        
        summary_data = [
            ['Total Sessions:', str(len(data))],
            ['Video Sessions:', str(video_count)],
            ['In-Person Sessions:', str(in_person_count)],
            ['Status Breakdown:', get_session_status_breakdown_text(data)]
        ]
        
        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # Main data section
        story.append(Paragraph("📅 Session Details", section_style))
        
        table_data = [['ID', 'Student', 'Status', 'Scheduled', 'Duration', 'Type']]
        
        for session in data:
            duration_text = f"{session.duration_minutes}min" if session.duration_minutes else 'N/A'
            type_text = '🎥 Video' if session.is_video_session else '👥 In-Person'
            status_text = session.status.replace('_', ' ').title()
            
            table_data.append([
                str(session.id),
                session.student.user.get_full_name(),
                status_text,
                session.scheduled_at.strftime('%m/%d/%Y %I:%M %p') if session.scheduled_at else 'N/A',
                duration_text,
                type_text
            ])
    
    # Enhanced table styling
    col_widths = [0.8*inch, 2.2*inch, 1.8*inch, 1.2*inch, 1.2*inch, 1.3*inch] if report_type == 'inquiries' else [0.6*inch, 2*inch, 1.2*inch, 1.8*inch, 0.8*inch, 1.1*inch]
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Data rows styling
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2d3748')),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # ID column center
        ('ALIGN', (1, 1), (-1, -1), 'LEFT'),   # Other columns left
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        
        # Grid and borders
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2b6cb0')),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    story.append(table)
    
    # Footer with generation info
    story.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#718096'),
        alignment=1,  # Center
    )
    story.append(Paragraph(f"Generated by KapiyuGuide System • {current_date} • Confidential", footer_style))
    
    doc.build(story)
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={report_type}_report.pdf'}
    )


def generate_summary_pdf(stats):
    """Generate enhanced summary PDF report"""
    output = io.BytesIO()
    
    # Custom page setup with margins
    doc = SimpleDocTemplate(
        output, 
        pagesize=A4,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch
    )
    story = []
    
    styles = getSampleStyleSheet()
    
    # Enhanced header styles
    main_title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Normal'],
        fontSize=28,
        textColor=colors.HexColor('#1a202c'),
        fontName='Helvetica-Bold',
        alignment=1,  # Center
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#4a5568'),
        fontName='Helvetica',
        alignment=1,  # Center
        spaceAfter=30
    )
    
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2b6cb0'),
        fontName='Helvetica-Bold',
        spaceBefore=25,
        spaceAfter=15,
        borderWidth=0,
        borderPadding=0,
        leftIndent=0
    )
    
    highlight_style = ParagraphStyle(
        'Highlight',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#2d3748'),
        fontName='Helvetica',
        alignment=1,
        spaceBefore=10,
        spaceAfter=20
    )
    
    # Header section with branding
    story.append(Paragraph("📊 KapiyuGuide Office Analytics", main_title_style))
    
    current_date = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    story.append(Paragraph(f"Monthly Summary Report - Generated on {current_date}", subtitle_style))
    
    # Add decorative line
    story.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor('#3182ce')))
    story.append(Spacer(1, 30))
    
    # Executive Summary Box
    story.append(Paragraph("📋 Executive Summary", section_title_style))
    
    # Calculate some insights
    total_interactions = stats['total_inquiries'] + stats['total_sessions']
    monthly_growth = ((stats['inquiries_this_month'] + stats['sessions_this_month']) / max(total_interactions, 1)) * 100
    
    summary_text = f"""
    <b>Total Student Interactions:</b> {total_interactions}<br/>
    <b>Monthly Activity Rate:</b> {monthly_growth:.1f}% of total volume<br/>
    <b>Response Efficiency:</b> {stats['response_rate']}% inquiry resolution rate<br/>
    <b>Service Quality:</b> {stats['avg_resolution_time']} average response time
    """
    
    summary_para = Paragraph(summary_text, highlight_style)
    story.append(summary_para)
    story.append(Spacer(1, 20))
    
    # Key Metrics Section
    story.append(Paragraph("📈 Key Performance Metrics", section_title_style))
    
    # Enhanced statistics table with better styling
    metrics_data = [
        ['📝 Student Inquiries', '', '🎯 Counseling Services', ''],
        ['Total Inquiries', f"{stats['total_inquiries']:,}", 'Total Sessions', f"{stats['total_sessions']:,}"],
        ['This Month', f"{stats['inquiries_this_month']:,}", 'This Month', f"{stats['sessions_this_month']:,}"],
        ['', '', '', ''],
        ['📊 Performance Indicators', '', '⏱️ Service Quality', ''],
        ['Response Rate', f"{stats['response_rate']}%", 'Avg Resolution Time', stats['avg_resolution_time']],
    ]
    
    metrics_table = Table(metrics_data, colWidths=[2.2*inch, 1.3*inch, 2.2*inch, 1.3*inch])
    metrics_table.setStyle(TableStyle([
        # Header rows styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#e2e8f0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 4), (-1, 4), colors.HexColor('#2d3748')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTSIZE', (0, 4), (-1, 4), 12),
        
        # Data rows styling
        ('FONTNAME', (0, 1), (-1, 3), 'Helvetica-Bold'),
        ('FONTNAME', (1, 1), (-1, 3), 'Helvetica'),
        ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
        ('FONTNAME', (1, 5), (-1, 5), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('TEXTCOLOR', (0, 1), (0, 3), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (2, 1), (2, 3), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (0, 5), (0, 5), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (2, 5), (2, 5), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (1, 1), (1, -1), colors.HexColor('#1a202c')),
        ('TEXTCOLOR', (3, 1), (3, -1), colors.HexColor('#1a202c')),
        
        # Alignment
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Borders and spacing
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#cbd5e0')),
        ('LINEBELOW', (0, 4), (-1, 4), 1, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        
        # Alternating backgrounds for data rows
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f7fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f7fafc')),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f7fafc')),
    ]))
    
    story.append(metrics_table)
    story.append(Spacer(1, 30))
    
    # Insights and Recommendations Section
    story.append(Paragraph("💡 Key Insights & Recommendations", section_title_style))
    
    # Generate dynamic insights based on data
    insights = []
    
    if stats['response_rate'] >= 80:
        insights.append("✅ <b>Excellent Response Rate:</b> Your team maintains a strong {:.1f}% response rate, indicating effective inquiry management.".format(stats['response_rate']))
    elif stats['response_rate'] >= 60:
        insights.append("⚠️ <b>Good Response Rate:</b> At {:.1f}%, there's room for improvement in inquiry response efficiency.".format(stats['response_rate']))
    else:
        insights.append("🔴 <b>Response Rate Attention Needed:</b> The {:.1f}% response rate suggests a need for process optimization.".format(stats['response_rate']))
    
    if stats['sessions_this_month'] > stats['inquiries_this_month']:
        insights.append("📈 <b>High Counseling Demand:</b> Counseling sessions exceed inquiry volume, indicating strong student engagement.")
    else:
        insights.append("📋 <b>Inquiry-Driven Activity:</b> Student inquiries are the primary engagement channel this month.")
    
    monthly_total = stats['inquiries_this_month'] + stats['sessions_this_month']
    if monthly_total > 50:
        insights.append("🚀 <b>High Activity Volume:</b> With {} total interactions this month, your office is highly active.".format(monthly_total))
    elif monthly_total > 20:
        insights.append("📊 <b>Moderate Activity:</b> {} interactions this month shows steady student engagement.".format(monthly_total))
    else:
        insights.append("📈 <b>Growth Opportunity:</b> {} interactions suggest potential for increased outreach and engagement.".format(monthly_total))
    
    for insight in insights:
        story.append(Paragraph(insight, ParagraphStyle(
            'Insight',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#2d3748'),
            fontName='Helvetica',
            spaceBefore=8,
            spaceAfter=8,
            leftIndent=20,
            bulletIndent=10
        )))
    
    story.append(Spacer(1, 30))
    
    # Footer section
    footer_box_style = ParagraphStyle(
        'FooterBox',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#718096'),
        fontName='Helvetica',
        alignment=1,
        spaceBefore=20
    )
    
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(Spacer(1, 10))
    
    footer_text = f"""
    <b>Report Generated:</b> {current_date}<br/>
    <b>System:</b> KapiyuGuide Office Management Platform<br/>
    <i>This report contains confidential information intended for authorized personnel only.</i>
    """
    
    story.append(Paragraph(footer_text, footer_box_style))
    
    doc.build(story)
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment; filename=office_summary_report.pdf'}
    )


def generate_summary_excel(stats):
    """Generate summary Excel report"""
    output = io.BytesIO()
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Summary Report"
    
    # Styling
    header_font = Font(bold=True, color="FFFFFF", size=14)
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    
    # Headers
    worksheet.cell(row=1, column=1, value="Metric").font = header_font
    worksheet.cell(row=1, column=1).fill = header_fill
    worksheet.cell(row=1, column=2, value="Value").font = header_font
    worksheet.cell(row=1, column=2).fill = header_fill
    
    # Data
    metrics = [
        ('Total Inquiries', stats['total_inquiries']),
        ('Inquiries This Month', stats['inquiries_this_month']),
        ('Total Counseling Sessions', stats['total_sessions']),
        ('Sessions This Month', stats['sessions_this_month']),
        ('Response Rate', f"{stats['response_rate']}%"),
        ('Average Resolution Time', stats['avg_resolution_time'])
    ]
    
    for row, (metric, value) in enumerate(metrics, 2):
        worksheet.cell(row=row, column=1, value=metric)
        worksheet.cell(row=row, column=2, value=value)
    
    # Auto-adjust column widths
    worksheet.column_dimensions['A'].width = 25
    worksheet.column_dimensions['B'].width = 20
    
    workbook.save(output)
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=summary_report.xlsx'}
    )


def get_status_breakdown_text(inquiries):
    """Get status breakdown text for inquiries"""
    status_counts = {}
    for inquiry in inquiries:
        status = inquiry.status.replace('_', ' ').title()
        status_counts[status] = status_counts.get(status, 0) + 1
    
    breakdown_parts = []
    for status, count in status_counts.items():
        breakdown_parts.append(f"{status}: {count}")
    
    return " | ".join(breakdown_parts) if breakdown_parts else "No data"


def get_session_status_breakdown_text(sessions):
    """Get status breakdown text for counseling sessions"""
    status_counts = {}
    for session in sessions:
        status = session.status.replace('_', ' ').title()
        status_counts[status] = status_counts.get(status, 0) + 1
    
    breakdown_parts = []
    for status, count in status_counts.items():
        breakdown_parts.append(f"{status}: {count}")
    
    return " | ".join(breakdown_parts) if breakdown_parts else "No data"
