from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from functools import wraps
from app.db import get_db
from app.utils import log_action, CLASSES_AND_UNITS
import secrets
import string

dept_admin_bp = Blueprint('dept_admin', __name__)


def dept_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('dept_admin', 'super_admin'):
            flash('Department Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def generate_temp_password(length=10):
    chars = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(chars) for _ in range(length))


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/dashboard')
@login_required
@dept_admin_required
def dashboard():
    db    = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    stats  = {}
    try:
        q_base = db.table('classes').select('id')
        if dep_id:
            q_base = q_base.eq('department_id', dep_id)
        stats['classes']  = len(q_base.execute().data or [])

        q_units = db.table('units').select('id, courses(department_id)')
        units_data = q_units.execute().data or []
        if dep_id:
            stats['units'] = sum(1 for u in units_data
                                 if u.get('courses', {}).get('department_id') == dep_id)
        else:
            stats['units'] = len(units_data)

        q_trainers = db.table('users').select('id').eq('role', 'trainer')
        q_trainees = db.table('users').select('id').eq('role', 'trainee')
        if dep_id:
            q_trainers = q_trainers.eq('department_id', dep_id)
            q_trainees = q_trainees.eq('department_id', dep_id)
        stats['trainers'] = len(q_trainers.execute().data or [])
        stats['trainees'] = len(q_trainees.execute().data or [])

        # Recent assessments
        recent = (db.table('assessments')
                  .select('*, users!assessments_trainee_id_fkey(full_name, admission_no), units(name), classes(name)')
                  .order('uploaded_at', desc=True)
                  .limit(10)
                  .execute().data or [])
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        recent = []

    return render_template('dept_admin/dashboard.html', stats=stats, recent=recent)


# ─────────────────────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/courses')
@login_required
@dept_admin_required
def courses():
    db     = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    q      = db.table('courses').select('*, departments(name)')
    if dep_id:
        q = q.eq('department_id', dep_id)
    data = q.order('name').execute().data or []
    deps = db.table('departments').select('*').order('name').execute().data or []
    return render_template('dept_admin/courses.html', courses=data, departments=deps)


@dept_admin_bp.route('/courses/add', methods=['POST'])
@login_required
@dept_admin_required
def add_course():
    db     = get_db()
    dep_id = request.form.get('department_id') or str(current_user.department_id)
    name   = request.form.get('name', '').strip()
    code   = request.form.get('code', '').strip().upper()
    if not name or not code or not dep_id:
        flash('All fields required.', 'danger')
        return redirect(url_for('dept_admin.courses'))
    try:
        db.table('courses').insert({
            'name': name, 'code': code,
            'department_id': dep_id,
            'created_by': str(current_user.id)
        }).execute()
        log_action('CREATE_COURSE', 'course', None, name)
        flash(f'Course "{name}" created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.courses'))


# ─────────────────────────────────────────────────────────────
# UNITS
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/units')
@login_required
@dept_admin_required
def units():
    db        = get_db()
    course_id = request.args.get('course_id', '')
    q         = db.table('units').select('*, courses(name, department_id, departments(name))')
    if course_id:
        q = q.eq('course_id', course_id)
    data    = q.order('name').execute().data or []
    courses = db.table('courses').select('*').order('name').execute().data or []
    return render_template('dept_admin/units.html', units=data, courses=courses, course_filter=course_id)


@dept_admin_bp.route('/units/add', methods=['POST'])
@login_required
@dept_admin_required
def add_unit():
    db        = get_db()
    course_id = request.form.get('course_id', '').strip()
    name      = request.form.get('name', '').strip()
    code      = request.form.get('code', '').strip().upper()
    if not course_id or not name:
        flash('Course and unit name are required.', 'danger')
        return redirect(url_for('dept_admin.units'))
    try:
        db.table('units').insert({
            'name': name, 'code': code or None,
            'course_id': course_id,
            'created_by': str(current_user.id)
        }).execute()
        log_action('CREATE_UNIT', 'unit', None, name)
        flash(f'Unit "{name}" created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.units'))


# ─────────────────────────────────────────────────────────────
# CLASSES
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/classes')
@login_required
@dept_admin_required
def classes():
    db     = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    q      = db.table('classes').select('*, courses(name), departments(name)')
    if dep_id:
        q = q.eq('department_id', dep_id)
    data    = q.order('name').execute().data or []
    courses = db.table('courses').select('*').order('name').execute().data or []
    deps    = db.table('departments').select('*').order('name').execute().data or []
    return render_template('dept_admin/classes.html', classes=data, courses=courses, departments=deps)


@dept_admin_bp.route('/classes/add', methods=['POST'])
@login_required
@dept_admin_required
def add_class():
    db     = get_db()
    dep_id = request.form.get('department_id') or str(current_user.department_id)
    name   = request.form.get('name', '').strip()
    course_id = request.form.get('course_id', '').strip()
    if not name or not course_id or not dep_id:
        flash('All fields required.', 'danger')
        return redirect(url_for('dept_admin.classes'))
    try:
        db.table('classes').insert({
            'name': name,
            'course_id': course_id,
            'department_id': dep_id,
            'intake_year': request.form.get('intake_year') or None,
            'intake_month': request.form.get('intake_month', '').strip() or None,
            'created_by': str(current_user.id)
        }).execute()
        log_action('CREATE_CLASS', 'class', None, name)
        flash(f'Class "{name}" created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.classes'))


@dept_admin_bp.route('/classes/<class_id>/units', methods=['GET', 'POST'])
@login_required
@dept_admin_required
def class_units(class_id):
    db = get_db()
    cls = db.table('classes').select('*, courses(name)').eq('id', class_id).single().execute().data
    if not cls:
        flash('Class not found.', 'danger')
        return redirect(url_for('dept_admin.classes'))

    if request.method == 'POST':
        unit_ids = request.form.getlist('unit_ids')
        # Remove existing, re-insert selected
        db.table('class_units').delete().eq('class_id', class_id).execute()
        for uid in unit_ids:
            try:
                db.table('class_units').insert({'class_id': class_id, 'unit_id': uid}).execute()
            except Exception:
                pass
        log_action('UPDATE_CLASS_UNITS', 'class', class_id, cls['name'])
        flash('Class units updated.', 'success')
        return redirect(url_for('dept_admin.classes'))

    all_units     = db.table('units').select('*').order('name').execute().data or []
    assigned_ids  = [cu['unit_id'] for cu in
                     db.table('class_units').select('unit_id').eq('class_id', class_id).execute().data or []]
    return render_template('dept_admin/class_units.html',
                           cls=cls, all_units=all_units, assigned_ids=assigned_ids)


# ─────────────────────────────────────────────────────────────
# TRAINER MANAGEMENT
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/trainers')
@login_required
@dept_admin_required
def trainers():
    db     = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    q      = db.table('users').select('*, departments(name)').eq('role', 'trainer')
    if dep_id:
        q = q.eq('department_id', dep_id)
    data = q.order('full_name').execute().data or []
    deps = db.table('departments').select('*').order('name').execute().data or []
    return render_template('dept_admin/trainers.html', trainers=data, departments=deps)


@dept_admin_bp.route('/trainers/add', methods=['POST'])
@login_required
@dept_admin_required
def add_trainer():
    db     = get_db()
    dep_id = request.form.get('department_id') or str(current_user.department_id)
    email  = request.form.get('email', '').strip().lower()
    name   = request.form.get('full_name', '').strip()
    staff  = request.form.get('staff_no', '').strip()
    temp_pw = generate_temp_password()

    if not email or not name:
        flash('Email and name are required.', 'danger')
        return redirect(url_for('dept_admin.trainers'))
    try:
        db.table('users').insert({
            'email': email,
            'full_name': name,
            'role': 'trainer',
            'department_id': dep_id,
            'staff_no': staff or None,
            'password_hash': generate_password_hash(temp_pw),
            'created_by': str(current_user.id),
            'is_active': True,
        }).execute()
        log_action('CREATE_TRAINER', 'user', None, name)
        flash(f'Trainer "{name}" created. Temp password: {temp_pw}', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.trainers'))


# ─────────────────────────────────────────────────────────────
# TRAINEE MANAGEMENT
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/trainees')
@login_required
@dept_admin_required
def trainees():
    db     = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    q      = db.table('users').select('*, departments(name)').eq('role', 'trainee')
    if dep_id:
        q = q.eq('department_id', dep_id)
    data    = q.order('full_name').execute().data or []
    deps    = db.table('departments').select('*').order('name').execute().data or []
    classes = db.table('classes').select('*').order('name').execute().data or []
    return render_template('dept_admin/trainees.html', trainees=data, departments=deps, classes=classes)


@dept_admin_bp.route('/trainees/add', methods=['POST'])
@login_required
@dept_admin_required
def add_trainee():
    db     = get_db()
    dep_id = request.form.get('department_id') or str(current_user.department_id)
    email  = request.form.get('email', '').strip().lower()
    name   = request.form.get('full_name', '').strip()
    adm_no = request.form.get('admission_no', '').strip()
    class_id = request.form.get('class_id', '').strip()
    temp_pw  = generate_temp_password()

    if not email or not name or not adm_no:
        flash('Email, name and admission number are required.', 'danger')
        return redirect(url_for('dept_admin.trainees'))
    if len(adm_no) != 5 or not adm_no.isdigit():
        flash('Admission number must be exactly 5 digits.', 'danger')
        return redirect(url_for('dept_admin.trainees'))
    try:
        result = db.table('users').insert({
            'email': email,
            'full_name': name,
            'role': 'trainee',
            'department_id': dep_id,
            'admission_no': adm_no,
            'password_hash': generate_password_hash(temp_pw),
            'created_by': str(current_user.id),
            'is_active': True,
        }).execute()

        if class_id and result.data:
            trainee_id = result.data[0]['id']
            try:
                db.table('enrollments').insert({
                    'trainee_id': trainee_id,
                    'class_id': class_id
                }).execute()
            except Exception:
                pass

        log_action('CREATE_TRAINEE', 'user', None, f'{name} ({adm_no})')
        flash(f'Trainee "{name}" created. Temp password: {temp_pw}', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.trainees'))


@dept_admin_bp.route('/trainees/delete/<trainee_id>', methods=['POST'])
@login_required
@dept_admin_required
def delete_trainee(trainee_id):
    try:
        get_db().table('users').delete().eq('id', trainee_id).execute()
        log_action('DELETE_TRAINEE', 'user', trainee_id)
        flash('Trainee deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('dept_admin.trainees'))


# ─────────────────────────────────────────────────────────────
# API: get units for a class (used by trainee upload form)
# ─────────────────────────────────────────────────────────────
@dept_admin_bp.route('/api/class-units/<class_id>')
@login_required
def api_class_units(class_id):
    db = get_db()
    rows = (db.table('class_units')
            .select('units(id, name)')
            .eq('class_id', class_id)
            .execute().data or [])
    units = [r['units'] for r in rows if r.get('units')]
    return jsonify({'units': units})
