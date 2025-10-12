from flask import request, redirect, url_for, render_template, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func

from app.office import office_bp
from app.utils import role_required
from app.models import (
    ConcernType, OfficeConcernType, CounselingSession, Office, db
)


@office_bp.route('/counseling-concern-types', methods=['GET', 'POST'])
@login_required
@role_required(['office_admin'])
def manage_counseling_concern_types():
    """Mirror of inquiry concern types page but focused on counseling usage stats.

    Re-uses ConcernType + OfficeConcernType models. The distinction is purely in the
    analytics layer: counts are based on CounselingSession.nature_of_concern_id rather
    than InquiryConcern links.
    """
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        flash('Access denied. You do not have permission to view this page.', 'error')
        return redirect(url_for('main.index'))

    office_id = current_user.office_admin.office_id
    office = Office.query.get(office_id)
    if not office:
        flash('Office not found.', 'error')
        return redirect(url_for('office.dashboard'))
    # Enforce Campus Admin counseling toggle
    if not bool(getattr(office, 'supports_video', False)):
        flash('Counseling is disabled for your office.', 'warning')
        return redirect(url_for('office.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = (request.form.get('concern_name') or '').strip()
            description = (request.form.get('concern_description') or '').strip()
            allows_other = request.form.get('allows_other') == 'on'
            if not name:
                flash('Please enter a concern type name.', 'error')
            elif len(name) > 100:
                flash('Concern type name must be 100 characters or less.', 'error')
            elif len(description) > 500:
                flash('Description must be 500 characters or less.', 'error')
            else:
                existing = ConcernType.query.filter(func.lower(ConcernType.name)==func.lower(name)).first()
                if existing:
                    assoc = OfficeConcernType.query.filter_by(office_id=office_id, concern_type_id=existing.id).first()
                    if assoc:
                        flash('Your office already supports this concern type.', 'error')
                    else:
                        db.session.add(OfficeConcernType(
                            office_id=office_id,
                            concern_type_id=existing.id,
                            for_inquiries=bool(request.form.get('also_inquiries') == 'on'),
                            for_counseling=True
                        ))
                        try:
                            db.session.commit()
                            flash(f'Added existing concern type "{name}".', 'success')
                            return redirect(url_for('office.manage_counseling_concern_types'))
                        except Exception as e:
                            db.session.rollback()
                            flash(f'An error occurred: {e}', 'error')
                else:
                    try:
                        ct = ConcernType(name=name, description=description, allows_other=allows_other)
                        db.session.add(ct)
                        db.session.flush()
                        db.session.add(OfficeConcernType(
                            office_id=office_id,
                            concern_type_id=ct.id,
                            for_inquiries=bool(request.form.get('also_inquiries') == 'on'),
                            for_counseling=True
                        ))
                        db.session.commit()
                        flash(f'Created and added concern type "{name}".', 'success')
                        return redirect(url_for('office.manage_counseling_concern_types'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred: {e}', 'error')
        elif action == 'edit':
            concern_type_id = request.form.get('concern_type_id')
            name = (request.form.get('concern_name') or '').strip()
            description = (request.form.get('concern_description') or '').strip()
            allows_other = request.form.get('allows_other') == 'on'
            assoc = OfficeConcernType.query.filter_by(office_id=office_id, concern_type_id=concern_type_id).first()
            if not assoc:
                flash('You cannot edit a concern type your office does not support.', 'error')
            else:
                ct = ConcernType.query.get(concern_type_id)
                if not ct:
                    flash('Concern type not found.', 'error')
                else:
                    duplicate = ConcernType.query.filter(func.lower(ConcernType.name)==func.lower(name), ConcernType.id!=ct.id).first()
                    if duplicate:
                        flash('Another concern type with this name already exists.', 'error')
                    else:
                        try:
                            ct.name = name
                            ct.description = description
                            ct.allows_other = allows_other
                            # This page always manages counseling flag
                            assoc.for_counseling = True
                            if 'toggle_inquiries' in request.form:
                                assoc.for_inquiries = bool(request.form.get('toggle_inquiries') == 'on')
                            db.session.commit()
                            flash('Concern type updated.', 'success')
                            return redirect(url_for('office.manage_counseling_concern_types'))
                        except Exception as e:
                            db.session.rollback()
                            flash(f'An error occurred: {e}', 'error')
        elif action == 'remove':
            concern_type_id = request.form.get('concern_type_id')
            assoc = OfficeConcernType.query.filter_by(office_id=office_id, concern_type_id=concern_type_id).first()
            if not assoc:
                flash('Concern type association not found.', 'error')
            else:
                # If counseling concern type is already used, archive instead of delete
                in_use = CounselingSession.query.filter_by(office_id=office_id, nature_of_concern_id=concern_type_id).first()
                try:
                    if in_use:
                        # Archive behavior: keep association but disable counseling visibility
                        if assoc.for_counseling:
                            assoc.for_counseling = False
                        db.session.commit()
                        flash('Archived counseling concern type. Existing data is preserved.', 'success')
                        return redirect(url_for('office.manage_counseling_concern_types'))
                    # Not in use: if still used for inquiries, just disable counseling; else remove association
                    if assoc.for_inquiries:
                        assoc.for_counseling = False
                    else:
                        db.session.delete(assoc)
                    db.session.commit()
                    flash('Removed support for concern type.', 'success')
                    return redirect(url_for('office.manage_counseling_concern_types'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred: {e}', 'error')
        elif action == 'auto_reply':
            # Share logic with inquiry page for per-office auto reply
            concern_type_id = request.form.get('concern_type_id')
            enabled_raw = request.form.get('auto_reply_enabled', 'off')
            message = (request.form.get('auto_reply_message') or '').strip()
            enabled = enabled_raw in ['true','on','1','yes']
            assoc = OfficeConcernType.query.filter_by(office_id=office_id, concern_type_id=concern_type_id).first()
            if not assoc:
                flash('Concern type association not found.', 'error')
            else:
                try:
                    if enabled and not message:
                        flash('Provide a message to enable auto-reply.', 'error')
                    else:
                        assoc.auto_reply_message = message
                        assoc.auto_reply_enabled = bool(enabled and message)
                        db.session.commit()
                        flash('Auto-reply settings saved.', 'success')
                        return redirect(url_for('office.manage_counseling_concern_types'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred: {e}', 'error')

    supported_concern_types = (
        db.session.query(ConcernType, OfficeConcernType)
        .join(OfficeConcernType, ConcernType.id==OfficeConcernType.concern_type_id)
        .filter(OfficeConcernType.office_id==office_id, OfficeConcernType.for_counseling.is_(True))
        .order_by(ConcernType.name)
        .all()
    )

    concern_stats = {}
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    for ct, assoc in supported_concern_types:
        total_sessions = db.session.query(func.count(CounselingSession.id)).filter(
            CounselingSession.office_id==office_id,
            CounselingSession.nature_of_concern_id==ct.id
        ).scalar()
        recent_sessions = db.session.query(func.count(CounselingSession.id)).filter(
            CounselingSession.office_id==office_id,
            CounselingSession.nature_of_concern_id==ct.id,
            CounselingSession.scheduled_at >= thirty_days_ago
        ).scalar()
        concern_stats[ct.id] = {
            'total_sessions': total_sessions,
            'recent_sessions': recent_sessions
        }

    most_active_concerns = sorted(
        [(ct_assoc[0], concern_stats[ct_assoc[0].id]) for ct_assoc in supported_concern_types],
        key=lambda x: x[1]['recent_sessions'],
        reverse=True
    )[:5]

    return render_template(
        'office/office_counseling_concern_types.html',
        office=office,
    supported_concern_types=[ct for ct, assoc in supported_concern_types],
        concern_stats=concern_stats,
        most_active_concerns=most_active_concerns
    )


@office_bp.route('/counseling-concern-types/<int:concern_type_id>')
@login_required
@role_required(['office_admin'])
def get_counseling_concern_type_details(concern_type_id):
    if not hasattr(current_user, 'office_admin') or not current_user.office_admin:
        return jsonify({'error': 'Access denied'}), 403
    office_id = current_user.office_admin.office_id
    assoc = OfficeConcernType.query.filter_by(office_id=office_id, concern_type_id=concern_type_id).first()
    if not assoc:
        return jsonify({'error': 'Concern type not found or not supported by your office'}), 404
    ct = ConcernType.query.get(concern_type_id)
    if not ct:
        return jsonify({'error': 'Concern type not found'}), 404
    return jsonify({
        'id': ct.id,
        'name': ct.name,
        'description': ct.description,
        'allows_other': ct.allows_other,
    'for_inquiries': assoc.for_inquiries,
        'status': 'success'
    })
