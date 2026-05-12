from flask import Blueprint, redirect, url_for, render_template, jsonify, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import (
    ConcernType, OfficeConcernType, InquiryConcern, Inquiry, 
    Office, db, OfficeAdmin
)
from app.utils import role_required
from sqlalchemy import func, case, or_
from app.office import office_bp


@office_bp.route('/concern-types', methods=['GET', 'POST'])
@login_required
@role_required(['office_admin'])
def manage_concern_types():
    """Page to manage concern types that this office supports"""
    # Helper to parse checkbox-like truthy values from forms
    def _is_truthy(val):
        if val is None:
            return False
        if isinstance(val, bool):
            return val
        return str(val).lower() in ['true', 'on', '1', 'yes']
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    office_id = current_user.office_admin.office_id
    office = Office.query.get(office_id)
    
    if not office:
        flash('Office not found.', 'error')
        return redirect(url_for('office.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            # Create new concern type for this office
            concern_name = request.form.get('concern_name', '').strip()
            concern_description = request.form.get('concern_description', '').strip()
            allows_other = _is_truthy(request.form.get('allows_other'))
            
            if not concern_name:
                flash('Please enter a concern type name.', 'error')
            elif len(concern_name) > 100:
                flash('Concern type name must be 100 characters or less.', 'error')
            elif len(concern_description) > 500:
                flash('Description must be 500 characters or less.', 'error')
            else:
                # Check if concern type with this name already exists
                existing_concern = ConcernType.query.filter_by(name=concern_name).first()
                
                if existing_concern:
                    # Check if this office already supports this concern type
                    existing_association = OfficeConcernType.query.filter_by(
                        office_id=office_id,
                        concern_type_id=existing_concern.id
                    ).first()
                    
                    if existing_association:
                        flash('Your office already supports this concern type.', 'error')
                    else:
                        # Add association to existing concern type
                        new_association = OfficeConcernType(
                            office_id=office_id,
                            concern_type_id=existing_concern.id,
                            for_inquiries=True,
                            for_counseling=_is_truthy(request.form.get('also_counseling'))
                        )
                        db.session.add(new_association)
                        
                        try:
                            db.session.commit()
                            flash(f'Successfully added support for "{concern_name}" concern type.', 'success')
                            return redirect(url_for('office.manage_concern_types'))
                        except Exception as e:
                            db.session.rollback()
                            flash(f'An error occurred: {str(e)}', 'error')
                else:
                    # Create new concern type and association
                    try:
                        new_concern_type = ConcernType(
                            name=concern_name,
                            description=concern_description,
                            allows_other=allows_other
                        )
                        db.session.add(new_concern_type)
                        db.session.flush()  # Get the ID
                        
                        # Create association
                        new_association = OfficeConcernType(
                            office_id=office_id,
                            concern_type_id=new_concern_type.id,
                            for_inquiries=True,
                            for_counseling=_is_truthy(request.form.get('also_counseling'))
                        )
                        db.session.add(new_association)
                        db.session.commit()
                        
                        flash(f'Successfully created and added "{concern_name}" concern type.', 'success')
                        return redirect(url_for('office.manage_concern_types'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'edit':
            # Edit existing concern type
            concern_type_id = request.form.get('concern_type_id')
            concern_name = request.form.get('concern_name', '').strip()
            concern_description = request.form.get('concern_description', '').strip()
            allows_other = _is_truthy(request.form.get('allows_other'))
            
            if not concern_type_id:
                flash('Invalid concern type.', 'error')
            elif not concern_name:
                flash('Please enter a concern type name.', 'error')
            elif len(concern_name) > 100:
                flash('Concern type name must be 100 characters or less.', 'error')
            elif len(concern_description) > 500:
                flash('Description must be 500 characters or less.', 'error')
            else:
                # Verify this office supports this concern type
                association = OfficeConcernType.query.filter_by(
                    office_id=office_id,
                    concern_type_id=concern_type_id
                ).first()
                
                if not association:
                    flash('You cannot edit a concern type that your office does not support.', 'error')
                else:
                    concern_type = ConcernType.query.get(concern_type_id)
                    if not concern_type:
                        flash('Concern type not found.', 'error')
                    else:
                        # Check if another concern type with this name exists
                        existing_concern = ConcernType.query.filter(
                            ConcernType.name == concern_name,
                            ConcernType.id != concern_type_id
                        ).first()
                        
                        if existing_concern:
                            flash('A concern type with this name already exists.', 'error')
                        else:
                            try:
                                concern_type.name = concern_name
                                concern_type.description = concern_description
                                concern_type.allows_other = allows_other
                                # Optional toggles
                                association.for_inquiries = True  # This page always manages inquiry types
                                # Respect counseling toggle if present in form (may not be present in UI)
                                if request.form.get('toggle_counseling') is not None:
                                    association.for_counseling = _is_truthy(request.form.get('toggle_counseling'))
                                db.session.commit()
                                
                                flash(f'Successfully updated "{concern_name}" concern type.', 'success')
                                return redirect(url_for('office.manage_concern_types'))
                            except Exception as e:
                                db.session.rollback()
                                flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'remove':
            # Remove concern type association from office
            concern_type_id = request.form.get('concern_type_id')
            
            if not concern_type_id:
                flash('Invalid concern type.', 'error')
            else:
                association = OfficeConcernType.query.filter_by(
                    office_id=office_id,
                    concern_type_id=concern_type_id
                ).first()
                
                if not association:
                    flash('Concern type association not found.', 'error')
                else:
                    # Check if any inquiries are using this concern type for this office (only relevant to inquiries context)
                    inquiries_using_concern = Inquiry.query.join(InquiryConcern).filter(
                        Inquiry.office_id == office_id,
                        InquiryConcern.concern_type_id == concern_type_id
                    ).first()
                    
                    if inquiries_using_concern:
                        flash('Cannot remove this concern type as it is being used by existing inquiries.', 'error')
                    else:
                        concern_type = ConcernType.query.get(concern_type_id)
                        concern_name = concern_type.name if concern_type else 'Unknown'
                        
                        try:
                            db.session.delete(association)
                            db.session.commit()
                            flash(f'Successfully removed support for "{concern_name}" concern type.', 'success')
                            return redirect(url_for('office.manage_concern_types'))
                        except Exception as e:
                            db.session.rollback()
                            flash(f'An error occurred: {str(e)}', 'error')
        
        elif action == 'auto_reply':
            # Enable/disable and set auto-reply message for this office's concern type
            concern_type_id = request.form.get('concern_type_id')
            enabled_raw = request.form.get('auto_reply_enabled', 'off')
            message = (request.form.get('auto_reply_message') or '').strip()
            enabled = enabled_raw in ['true', 'on', '1', 'yes']

            if not concern_type_id:
                flash('Invalid concern type.', 'error')
            else:
                association = OfficeConcernType.query.filter_by(
                    office_id=office_id,
                    concern_type_id=concern_type_id
                ).first()
                if not association:
                    flash('Concern type association not found.', 'error')
                else:
                    try:
                        # Validation: cannot enable without a message
                        if enabled and not message:
                            flash('Please provide an auto-reply message to enable auto-reply.', 'error')
                            return redirect(url_for('office.manage_concern_types'))

                        # Always persist the message so admins can keep a draft even when disabled
                        association.auto_reply_message = message
                        # Only enable if explicitly requested and a message exists
                        association.auto_reply_enabled = bool(enabled and message)
                        db.session.commit()
                        if association.auto_reply_enabled:
                            flash('Auto-reply enabled and saved.', 'success')
                        elif message:
                            flash('Auto-reply draft saved (currently disabled).', 'success')
                        else:
                            flash('Auto-reply disabled and cleared.', 'success')
                        return redirect(url_for('office.manage_concern_types'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred: {str(e)}', 'error')
    
    # Get all concern types supported by this office
    supported_concern_types = db.session.query(ConcernType, OfficeConcernType).join(
        OfficeConcernType,
        ConcernType.id == OfficeConcernType.concern_type_id
    ).filter(
        OfficeConcernType.office_id == office_id,
        OfficeConcernType.for_inquiries.is_(True)
    ).order_by(ConcernType.name).all()
    
    # Get usage statistics for each supported concern type
    concern_stats = {}
    for concern_type, assoc in supported_concern_types:
        # Count inquiries using this concern type for this office
        inquiry_count = db.session.query(func.count(Inquiry.id)).join(
            InquiryConcern,
            Inquiry.id == InquiryConcern.inquiry_id
        ).filter(
            Inquiry.office_id == office_id,
            InquiryConcern.concern_type_id == concern_type.id
        ).scalar()

        # Count inquiries in the last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_inquiry_count = db.session.query(func.count(Inquiry.id)).join(
            InquiryConcern,
            Inquiry.id == InquiryConcern.inquiry_id
        ).filter(
            Inquiry.office_id == office_id,
            InquiryConcern.concern_type_id == concern_type.id,
            Inquiry.created_at >= thirty_days_ago
        ).scalar()

        concern_stats[concern_type.id] = {
            'total_inquiries': inquiry_count,
            'recent_inquiries': recent_inquiry_count
        }
    
    # Get most active concern types (top 5)
    most_active_concerns = sorted(
        [ (ct_assoc[0], concern_stats[ct_assoc[0].id]) for ct_assoc in supported_concern_types ],
        key=lambda x: x[1]['recent_inquiries'], reverse=True
    )[:5]
    
    return render_template(
        'office/office_concern_types.html',
    office=office,
    supported_concern_types=[ct for ct, assoc in supported_concern_types],
        concern_stats=concern_stats,
        most_active_concerns=most_active_concerns
    )


@office_bp.route('/concern-types/<int:concern_type_id>')
@login_required
@role_required(['office_admin'])
def get_concern_type_details(concern_type_id):
    """API endpoint to get concern type details for editing"""
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Verify this office supports this concern type
    association = OfficeConcernType.query.filter_by(
        office_id=office_id,
        concern_type_id=concern_type_id
    ).first()
    
    if not association:
        return jsonify({'error': 'Concern type not found or not supported by your office'}), 404
    
    concern_type = ConcernType.query.get(concern_type_id)
    if not concern_type:
        return jsonify({'error': 'Concern type not found'}), 404
    
    return jsonify({
        'id': concern_type.id,
        'name': concern_type.name,
        'description': concern_type.description,
        'allows_other': concern_type.allows_other,
    'for_counseling': association.for_counseling,
        'status': 'success'
    })


@office_bp.route('/concern-types/stats')
@login_required
@role_required(['office_admin'])
def concern_type_stats():
    """Get concern type statistics for charts"""
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    office_id = current_user.office_admin.office_id
    
    # Get concern type usage over time (last 12 months)
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    
    # Monthly statistics
    monthly_stats = db.session.query(
        func.date_trunc('month', Inquiry.created_at).label('month'),
        ConcernType.name,
        func.count(Inquiry.id).label('count')
    ).join(
        InquiryConcern,
        Inquiry.id == InquiryConcern.inquiry_id
    ).join(
        ConcernType,
        InquiryConcern.concern_type_id == ConcernType.id
    ).join(
        OfficeConcernType,
        ConcernType.id == OfficeConcernType.concern_type_id
    ).filter(
        Inquiry.office_id == office_id,
        OfficeConcernType.office_id == office_id,
        Inquiry.created_at >= twelve_months_ago
    ).group_by(
        func.date_trunc('month', Inquiry.created_at),
        ConcernType.name
    ).order_by(
        func.date_trunc('month', Inquiry.created_at)
    ).all()
    
    # Format data for charts
    chart_data = {}
    for stat in monthly_stats:
        month_str = stat.month.strftime('%Y-%m')
        if month_str not in chart_data:
            chart_data[month_str] = {}
        chart_data[month_str][stat.name] = stat.count
    
    return jsonify({
        'monthly_stats': chart_data,
        'status': 'success'
    })
