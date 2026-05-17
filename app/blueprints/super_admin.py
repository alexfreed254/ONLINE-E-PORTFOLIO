from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from functools import wraps
from app.db import get_db
from app.utils import log_action, format_bytes
from datetime import datetime

super_admin_bp = Blueprint('super_admin', __name__)


def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Super Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/dashboard')
@login_required
@super_admin_required
def dashboard():
    db = get_db()
    stats = {}
    try:
        stats['departments'] = len(db.table('departments').select('id').execute().data or [])
        stats['users']       = len(db.table('users').select('id').execute().data or [])
        stats['assessments'] = len(db.table('assessments').select('id').execute().data or [])
        stats['classes']     = len(db.table('classes').select('id').execute().data or [])

        # Counts by role
        all_users = db.table('users').select('role').execute().data or []
        stats['dept_admins'] = sum(1 for u in all_users if u['role'] == 'dept_admin')
        stats['trainers']    = sum(1 for u in all_users if u['role'] == 'trainer')
        stats['trainees']    = sum(1 for u in all_users if u['role'] == 'trainee')

        # Assessment status counts
        all_assess = db.table('assessments').select('status').execute().data or []
        stats['pending']  = sum(1 for a in all_assess if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_assess if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_assess if a['status'] == 'rejected')

        # Recent logs
        recent_logs = (db.table('system_logs')
                       .select('*, users(full_name, role)')
                       .order('created_at', desc=True)
                       .limit(20)
                       .execute().data or [])
    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'danger')
        recent_logs = []

    return render_template('super_admin/dashboard.html', stats=stats, recent_logs=recent_logs)


# ─────────────────────────────────────────────────────────────
# DEPARTMENTS
# ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/departments')
@login_required
@super_admin_required
def departments():
    db   = get_db()
    deps = db.table('departments').select('*').order('name').execute().data or []
    return render_template('super_admin/departments.html', departments=deps)


@super_admin_bp.route('/departments/add', methods=['POST'])
@login_required
@super_admin_required
def add_department():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    if not name or not code:
        flash('Name and code are required.', 'danger')
        return redirect(url_for('super_admin.departments'))
    try:
        get_db().table('departments').insert({'name': name, 'code': code}).execute()
        log_action('CREATE_DEPARTMENT', 'department', None, name)
        flash(f'Department "{name}" created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('super_admin.departments'))


@super_admin_bp.route('/departments/delete/<dep_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_department(dep_id):
    try:
        get_db().table('departments').delete().eq('id', dep_id).execute()
        log_action('DELETE_DEPARTMENT', 'department', dep_id)
        flash('Department deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('super_admin.departments'))


# ─────────────────────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/users')
@login_required
@super_admin_required
def users():
    db   = get_db()
    role = request.args.get('role', '')
    q    = db.table('users').select('*, departments(name)')
    if role:
        q = q.eq('role', role)
    all_users = q.order('full_name').execute().data or []
    deps      = db.table('departments').select('*').order('name').execute().data or []
    return render_template('super_admin/users.html', users=all_users, departments=deps, role_filter=role)


@super_admin_bp.route('/users/add', methods=['POST'])
@login_required
@super_admin_required
def add_user():
    db   = get_db()
    data = {
        'email':         request.form.get('email', '').strip().lower(),
        'full_name':     request.form.get('full_name', '').strip(),
        'role':          request.form.get('role', ''),
        'department_id': request.form.get('department_id') or None,
        'admission_no':  request.form.get('admission_no', '').strip() or None,
        'staff_no':      request.form.get('staff_no', '').strip() or None,
        'password_hash': '',  # set after validation
        'created_by':    str(current_user.id),
        'is_active':     True,
    }
    if not data['email'] or not data['full_name'] or not data['role']:
        flash('Email, name and role are required.', 'danger')
        return redirect(url_for('super_admin.users'))
    pw = request.form.get('password', '').strip()
    if len(pw) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('super_admin.users'))
    data['password_hash'] = generate_password_hash(pw)
    if data['role'] == 'trainee':
        adm = data.get('admission_no') or ''
        if not adm.isdigit() or len(adm) != 5:
            flash('Trainees require a 5-digit admission number.', 'danger')
            return redirect(url_for('super_admin.users'))
    try:
        db.table('users').insert(data).execute()
        log_action('CREATE_USER', 'user', None, f"{data['full_name']} ({data['role']})")
        flash(f"User {data['full_name']} created.", 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('super_admin.users'))


@super_admin_bp.route('/users/toggle/<user_id>', methods=['POST'])
@login_required
@super_admin_required
def toggle_user(user_id):
    db   = get_db()
    user = db.table('users').select('is_active, full_name').eq('id', user_id).single().execute().data
    if user:
        new_state = not user['is_active']
        db.table('users').update({'is_active': new_state}).eq('id', user_id).execute()
        action = 'ACTIVATE_USER' if new_state else 'DEACTIVATE_USER'
        log_action(action, 'user', user_id, user['full_name'])
        flash(f"User {'activated' if new_state else 'deactivated'}.", 'success')
    return redirect(url_for('super_admin.users'))


@super_admin_bp.route('/users/reset-password/<user_id>', methods=['POST'])
@login_required
@super_admin_required
def reset_password(user_id):
    new_pw = request.form.get('new_password', 'Password@123')
    get_db().table('users').update({'password_hash': generate_password_hash(new_pw)}).eq('id', user_id).execute()
    log_action('RESET_PASSWORD', 'user', user_id)
    flash('Password reset successfully.', 'success')
    return redirect(url_for('super_admin.users'))


@super_admin_bp.route('/users/delete/<user_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_user(user_id):
    try:
        get_db().table('users').delete().eq('id', user_id).execute()
        log_action('DELETE_USER', 'user', user_id)
        flash('User deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('super_admin.users'))


# ─────────────────────────────────────────────────────────────
# SYSTEM LOGS
# ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/logs')
@login_required
@super_admin_required
def logs():
    db      = get_db()
    page    = int(request.args.get('page', 1))
    per_page = 50
    offset  = (page - 1) * per_page

    logs_data = (db.table('system_logs')
                 .select('*, users(full_name, role)')
                 .order('created_at', desc=True)
                 .range(offset, offset + per_page - 1)
                 .execute().data or [])

    total = len(db.table('system_logs').select('id').execute().data or [])
    pages = (total + per_page - 1) // per_page

    return render_template('super_admin/logs.html',
                           logs=logs_data, page=page, pages=pages, total=total)


@super_admin_bp.route('/logs/clear', methods=['POST'])
@login_required
@super_admin_required
def clear_logs():
    try:
        get_db().table('system_logs').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        log_action('CLEAR_LOGS', 'system_logs', None, 'All logs cleared by super admin')
        flash('System logs cleared.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('super_admin.logs'))


# ─────────────────────────────────────────────────────────────
# ALL ASSESSMENTS VIEW
# ─────────────────────────────────────────────────────────────
@super_admin_bp.route('/assessments')
@login_required
@super_admin_required
def assessments():
    db     = get_db()
    status = request.args.get('status', '')
    q      = db.table('assessments').select(
        '*, users!assessments_trainee_id_fkey(full_name, admission_no), classes(name), units(name)'
    )
    if status:
        q = q.eq('status', status)
    data = q.order('uploaded_at', desc=True).execute().data or []
    return render_template('super_admin/assessments.html', assessments=data, status_filter=status)
