from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from app.admin import admin_bp
from app.models import db, Department, SuperAdminActivityLog, Campus


def _get_current_campus_id():
    """Resolve campus id for the current super_admin user."""
    if current_user.role == 'super_admin':
        return current_user.campus_id
    return None


@admin_bp.route('/departments', methods=['GET'])
@login_required
def manage_departments():
    if current_user.role != 'super_admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))

    campus_id = _get_current_campus_id()
    if not campus_id:
        flash('No campus is associated with your account.', 'error')
        return redirect(url_for('admin.dashboard'))

    departments = Department.query.filter_by(campus_id=campus_id).order_by(func.lower(Department.name)).all()
    campus = Campus.query.get(campus_id)
    return render_template('admin/departments.html', departments=departments, campus=campus)


@admin_bp.route('/api/departments', methods=['GET'])
@login_required
def api_departments():
    if current_user.role != 'super_admin':
        return jsonify([])
    campus_id = _get_current_campus_id()
    if not campus_id:
        return jsonify([])
    items = Department.query.filter_by(campus_id=campus_id, is_active=True).order_by(func.lower(Department.name)).all()
    return jsonify([
        {
            'id': d.id,
            'name': d.name,
            'code': d.code,
            'description': d.description
        } for d in items
    ])


@admin_bp.route('/departments', methods=['POST'])
@login_required
def create_department():
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Forbidden'}), 403
    campus_id = _get_current_campus_id()
    if not campus_id:
        return jsonify({'error': 'Campus not found for admin'}), 400

    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip() or None
    description = (data.get('description') or '').strip() or None

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    # Uniqueness per campus
    exists = Department.query.filter(
        Department.campus_id == campus_id,
        func.lower(Department.name) == func.lower(name)
    ).first()
    if exists:
        return jsonify({'error': f'Department "{name}" already exists.'}), 409

    dept = Department(campus_id=campus_id, name=name, code=code, description=description, is_active=True)
    db.session.add(dept)

    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action='Created department',
        target_type='department',
        details=f'Created department {name} ({code or "no code"})'
    )

    try:
        db.session.commit()
        return jsonify({'message': 'Created', 'department': {
            'id': dept.id,
            'name': dept.name,
            'code': dept.code,
            'description': dept.description,
            'is_active': dept.is_active
        }}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/departments/<int:dept_id>', methods=['PUT', 'PATCH'])
@login_required
def update_department(dept_id):
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Forbidden'}), 403
    campus_id = _get_current_campus_id()
    if not campus_id:
        return jsonify({'error': 'Campus not found for admin'}), 400

    dept = Department.query.filter_by(id=dept_id, campus_id=campus_id).first()
    if not dept:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    code = data.get('code')
    description = data.get('description')
    is_active = data.get('is_active')

    if name is not None:
        name = name.strip()
        if not name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        conflict = Department.query.filter(
            Department.campus_id == campus_id,
            func.lower(Department.name) == func.lower(name),
            Department.id != dept.id
        ).first()
        if conflict:
            return jsonify({'error': f'Another department named "{name}" exists.'}), 409
        old_name = dept.name
        dept.name = name
    if code is not None:
        code = code.strip() or None
        if code:
            conflict = Department.query.filter(
                Department.campus_id == campus_id,
                func.lower(Department.code) == func.lower(code),
                Department.id != dept.id
            ).first()
            if conflict:
                return jsonify({'error': f'Code "{code}" already in use.'}), 409
        dept.code = code
    if description is not None:
        dept.description = (description or '').strip() or None
    if is_active is not None:
        dept.is_active = bool(is_active)

    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action='Updated department',
        target_type='department',
        details=f'Updated department #{dept.id}'
    )

    try:
        db.session.commit()
        return jsonify({'message': 'Updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/departments/<int:dept_id>', methods=['DELETE'])
@login_required
def delete_department(dept_id):
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Forbidden'}), 403
    campus_id = _get_current_campus_id()
    if not campus_id:
        return jsonify({'error': 'Campus not found for admin'}), 400

    dept = Department.query.filter_by(id=dept_id, campus_id=campus_id).first()
    if not dept:
        return jsonify({'error': 'Not found'}), 404

    # In future, guard if linked to Students. For now we allow deletion.
    name = dept.name
    db.session.delete(dept)

    SuperAdminActivityLog.log_action(
        super_admin=current_user,
        action='Deleted department',
        target_type='department',
        details=f'Deleted department {name}'
    )

    try:
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
