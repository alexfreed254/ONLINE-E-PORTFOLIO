from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from app.db import get_db
from app.utils import (log_action, format_bytes, generate_unit_report_csv,
                       delete_from_storage, STORAGE_BUCKET_SCRIPTS, STORAGE_BUCKET_EVIDENCE,
                       get_storage_public_url)

trainer_bp = Blueprint('trainer', __name__)

SIDEBAR_COLOR = 'bg-emerald-800'


def trainer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('trainer', 'dept_admin', 'super_admin'):
            flash('Trainer access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _trainer_assigned_unit_ids(db) -> list:
    """Return list of unit_ids this trainer is assigned to. Empty = no restriction."""
    if current_user.role != 'trainer':
        return []          # dept_admin / super_admin see everything
    rows = (db.table('trainer_units').select('unit_id')
            .eq('trainer_id', str(current_user.id)).execute().data or [])
    return [r['unit_id'] for r in rows]


def _check_unit_access(db, unit_id: str) -> bool:
    """Return True if current trainer is allowed to act on this unit."""
    if current_user.role != 'trainer':
        return True
    assigned = _trainer_assigned_unit_ids(db)
    if not assigned:
        return True        # no assignments configured yet — allow all
    return unit_id in assigned


def _rename_script_file(db, assessment_id: str, action: str, trainer_name: str):
    """
    Append '— approved by <Trainer> — <TraineeName>' or
           '— rejected by <Trainer> — <TraineeName>'
    to the script_file_name stored in the DB (cosmetic label only; Storage path unchanged).
    """
    try:
        a = (db.table('assessments')
             .select('script_file_name, trainee_id')
             .eq('id', assessment_id).single().execute().data)
        if not a:
            return
        trainee = (db.table('users').select('full_name')
                   .eq('id', a['trainee_id']).single().execute().data)
        trainee_name = trainee['full_name'] if trainee else 'Trainee'

        original = a.get('script_file_name', '')
        # Strip any previous approval/rejection suffix
        import re
        original = re.sub(r'\s*[—–-]+\s*(approved|rejected) by .+$', '', original, flags=re.IGNORECASE)
        # Remove .pdf extension, append suffix, re-add extension
        base = original[:-4] if original.lower().endswith('.pdf') else original
        suffix = f' — {action} by {trainer_name} — {trainee_name}'
        new_name = base + suffix + '.pdf'
        db.table('assessments').update({'script_file_name': new_name}).eq('id', assessment_id).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/dashboard')
@login_required
@trainer_required
def dashboard():
    db     = get_db()
    stats  = {}
    try:
        assigned_unit_ids = _trainer_assigned_unit_ids(db)

        q = db.table('assessments').select('status')
        if assigned_unit_ids:
            q = q.in_('unit_id', assigned_unit_ids)
        elif current_user.role == 'trainer':
            # Trainer with no units assigned — show nothing
            q = q.eq('unit_id', 'none')

        all_a = q.execute().data or []
        stats['total']    = len(all_a)
        stats['pending']  = sum(1 for a in all_a if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_a if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_a if a['status'] == 'rejected')

        q2 = (db.table('assessments')
              .select('*, users!assessments_trainee_id_fkey(full_name, admission_no), units(name), classes(name)')
              .eq('status', 'pending')
              .order('uploaded_at', desc=True)
              .limit(15))
        if assigned_unit_ids:
            q2 = q2.in_('unit_id', assigned_unit_ids)
        elif current_user.role == 'trainer':
            q2 = q2.eq('unit_id', 'none')
        recent_pending = q2.execute().data or []

        # Units this trainer is assigned to (for quick CSV)
        if assigned_unit_ids:
            units_list = (db.table('units').select('id, name')
                          .in_('id', assigned_unit_ids).order('name').execute().data or [])
        elif current_user.role != 'trainer':
            units_list = db.table('units').select('id, name').order('name').limit(50).execute().data or []
        else:
            units_list = []

    except Exception as e:
        flash(f'Error: {e}', 'danger')
        recent_pending = []
        units_list     = []
        stats = {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0}

    return render_template('trainer/dashboard.html',
                           stats=stats, recent_pending=recent_pending, units_list=units_list)


# ─────────────────────────────────────────────────────────────
# BROWSE — Class → Unit → Files
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/browse')
@login_required
@trainer_required
def browse():
    db     = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    q      = db.table('classes').select('*, departments(name)')
    if dep_id:
        q = q.eq('department_id', dep_id)
    classes = q.order('name').execute().data or []
    return render_template('trainer/browse.html', classes=classes)


@trainer_bp.route('/browse/<class_id>')
@login_required
@trainer_required
def browse_class(class_id):
    db  = get_db()
    cls = db.table('classes').select('*, departments(name)').eq('id', class_id).single().execute().data
    if not cls:
        flash('Class not found.', 'danger')
        return redirect(url_for('trainer.browse'))

    assigned_unit_ids = _trainer_assigned_unit_ids(db)

    units_raw = (db.table('class_units').select('units(id, name)')
                 .eq('class_id', class_id).execute().data or [])
    units = [r['units'] for r in units_raw if r.get('units')]

    # Filter to assigned units only (for trainers)
    if assigned_unit_ids:
        units = [u for u in units if u['id'] in assigned_unit_ids]

    for unit in units:
        counts = (db.table('assessments').select('status')
                  .eq('class_id', class_id).eq('unit_id', unit['id'])
                  .execute().data or [])
        unit['total']    = len(counts)
        unit['pending']  = sum(1 for c in counts if c['status'] == 'pending')
        unit['approved'] = sum(1 for c in counts if c['status'] == 'approved')
        unit['rejected'] = sum(1 for c in counts if c['status'] == 'rejected')

    return render_template('trainer/browse_class.html', cls=cls, units=units)


@trainer_bp.route('/browse/<class_id>/<unit_id>')
@login_required
@trainer_required
def browse_unit(class_id, unit_id):
    db   = get_db()
    cls  = db.table('classes').select('*').eq('id', class_id).single().execute().data
    unit = db.table('units').select('*').eq('id', unit_id).single().execute().data
    if not cls or not unit:
        flash('Not found.', 'danger')
        return redirect(url_for('trainer.browse'))

    if not _check_unit_access(db, unit_id):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.browse_class', class_id=class_id))

    status_filter = request.args.get('status', '')
    q = (db.table('assessments')
         .select('*, users!assessments_trainee_id_fkey(full_name, admission_no)')
         .eq('class_id', class_id).eq('unit_id', unit_id))
    if status_filter:
        q = q.eq('status', status_filter)
    assessments = q.order('uploaded_at', desc=True).execute().data or []

    for a in assessments:
        ev = db.table('evidence').select('id').eq('assessment_id', a['id']).execute().data or []
        a['evidence_count']       = len(ev)
        a['script_file_size_fmt'] = format_bytes(a.get('script_file_size', 0))

    return render_template('trainer/browse_unit.html',
                           cls=cls, unit=unit, assessments=assessments,
                           status_filter=status_filter)


# ─────────────────────────────────────────────────────────────
# ASSESSMENT DETAIL
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>')
@login_required
@trainer_required
def assessment_detail(assessment_id):
    db = get_db()
    a  = (db.table('assessments')
          .select('*, users!assessments_trainee_id_fkey(full_name, admission_no, email), units(name), classes(name)')
          .eq('id', assessment_id).single().execute().data)
    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    if not _check_unit_access(db, a.get('unit_id', '')):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    evidence = (db.table('evidence').select('*')
                .eq('assessment_id', assessment_id).order('uploaded_at').execute().data or [])

    # Build public URLs for evidence
    for ev in evidence:
        ev['public_url'] = get_storage_public_url(STORAGE_BUCKET_EVIDENCE, ev.get('file_path', ''))

    script_url = get_storage_public_url(STORAGE_BUCKET_SCRIPTS, a.get('script_file_path', ''))

    reviewer = None
    if a.get('reviewed_by'):
        rev = db.table('users').select('full_name').eq('id', a['reviewed_by']).single().execute().data
        reviewer = rev['full_name'] if rev else None

    return render_template('trainer/assessment_detail.html',
                           assessment=a, evidence=evidence, reviewer=reviewer,
                           script_url=script_url, format_bytes=format_bytes)


# ─────────────────────────────────────────────────────────────
# APPROVE
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>/approve', methods=['POST'])
@login_required
@trainer_required
def approve_assessment(assessment_id):
    db   = get_db()
    note = request.form.get('note', '').strip()

    a = db.table('assessments').select('unit_id, status').eq('id', assessment_id).single().execute().data
    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainer.dashboard'))
    if not _check_unit_access(db, a.get('unit_id', '')):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    db.table('assessments').update({
        'status':      'approved',
        'reviewed_by': str(current_user.id),
        'reviewed_at': datetime.utcnow().isoformat(),
        'review_note': note or None,
        'updated_at':  datetime.utcnow().isoformat(),
    }).eq('id', assessment_id).execute()

    # Append trainer name + trainee name to the file label
    _rename_script_file(db, assessment_id, 'approved', current_user.full_name)

    log_action('APPROVE_ASSESSMENT', 'assessment', assessment_id,
               f'Approved by {current_user.full_name}')
    flash('Assessment approved.', 'success')
    return redirect(request.referrer or url_for('trainer.dashboard'))


# ─────────────────────────────────────────────────────────────
# REJECT
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>/reject', methods=['POST'])
@login_required
@trainer_required
def reject_assessment(assessment_id):
    db   = get_db()
    note = request.form.get('note', '').strip()

    a = db.table('assessments').select('unit_id, status').eq('id', assessment_id).single().execute().data
    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainer.dashboard'))
    if not _check_unit_access(db, a.get('unit_id', '')):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    db.table('assessments').update({
        'status':      'rejected',
        'reviewed_by': str(current_user.id),
        'reviewed_at': datetime.utcnow().isoformat(),
        'review_note': note or 'Rejected by trainer.',
        'updated_at':  datetime.utcnow().isoformat(),
    }).eq('id', assessment_id).execute()

    _rename_script_file(db, assessment_id, 'rejected', current_user.full_name)

    log_action('REJECT_ASSESSMENT', 'assessment', assessment_id,
               f'Rejected by {current_user.full_name}')
    flash('Assessment rejected.', 'warning')
    return redirect(request.referrer or url_for('trainer.dashboard'))


# ─────────────────────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>/delete', methods=['POST'])
@login_required
@trainer_required
def delete_assessment(assessment_id):
    db = get_db()
    a  = db.table('assessments').select('script_file_path, unit_id').eq('id', assessment_id).single().execute().data
    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainer.dashboard'))
    if not _check_unit_access(db, a.get('unit_id', '')):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    if a.get('script_file_path'):
        delete_from_storage(STORAGE_BUCKET_SCRIPTS, a['script_file_path'])
    evs = db.table('evidence').select('file_path').eq('assessment_id', assessment_id).execute().data or []
    for ev in evs:
        delete_from_storage(STORAGE_BUCKET_EVIDENCE, ev['file_path'])
    db.table('assessments').delete().eq('id', assessment_id).execute()
    log_action('DELETE_ASSESSMENT', 'assessment', assessment_id)
    flash('Assessment deleted.', 'success')
    return redirect(request.referrer or url_for('trainer.dashboard'))


# ─────────────────────────────────────────────────────────────
# CSV REPORT DOWNLOAD
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/download-unit-report/<unit_id>')
@login_required
@trainer_required
def download_unit_report(unit_id):
    db = get_db()
    if not _check_unit_access(db, unit_id):
        flash('You are not assigned to this unit.', 'danger')
        return redirect(url_for('trainer.dashboard'))
    try:
        dep_id   = str(current_user.department_id) if current_user.department_id else None
        csv_data = generate_unit_report_csv(unit_id, department_id=dep_id)
        unit     = db.table('units').select('name').eq('id', unit_id).single().execute().data
        name     = unit['name'].replace(' ', '_') if unit else 'Unit'
        resp     = make_response(csv_data)
        resp.headers['Content-Disposition'] = f'attachment; filename="report_{name}.csv"'
        resp.headers['Content-type'] = 'text/csv'
        return resp
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('trainer.dashboard'))


# ─────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/search')
@login_required
@trainer_required
def search():
    db                = get_db()
    assigned_unit_ids = _trainer_assigned_unit_ids(db)
    dep_id            = str(current_user.department_id) if current_user.department_id else None

    q_cls = db.table('classes').select('*')
    if dep_id:
        q_cls = q_cls.eq('department_id', dep_id)
    classes = q_cls.order('name').execute().data or []

    if assigned_unit_ids:
        units = (db.table('units').select('*')
                 .in_('id', assigned_unit_ids).order('name').execute().data or [])
    else:
        units = db.table('units').select('*').order('name').execute().data or []

    return render_template('trainer/search.html', classes=classes, units=units)


@trainer_bp.route('/search/results')
@login_required
@trainer_required
def search_results():
    db                = get_db()
    assigned_unit_ids = _trainer_assigned_unit_ids(db)
    adm     = request.args.get('adm', '').strip()
    cls_id  = request.args.get('class_id', '').strip()
    unit_id = request.args.get('unit_id', '').strip()
    status  = request.args.get('status', '').strip()
    year    = request.args.get('year', '').strip()

    # Enforce unit restriction
    if unit_id and assigned_unit_ids and unit_id not in assigned_unit_ids:
        return jsonify({'assessments': [], 'total': 0})

    q = db.table('assessments').select(
        '*, users!assessments_trainee_id_fkey(full_name, admission_no), units(name), classes(name)'
    )
    if adm:
        trainees = db.table('users').select('id').eq('admission_no', adm).execute().data or []
        if trainees:
            q = q.eq('trainee_id', trainees[0]['id'])
        else:
            return jsonify({'assessments': [], 'total': 0})
    if cls_id:
        q = q.eq('class_id', cls_id)
    if unit_id:
        q = q.eq('unit_id', unit_id)
    elif assigned_unit_ids:
        q = q.in_('unit_id', assigned_unit_ids)
    if status:
        q = q.eq('status', status)
    if year:
        try:
            q = q.eq('year', int(year))
        except ValueError:
            pass

    results = q.order('uploaded_at', desc=True).execute().data or []
    for r in results:
        r['script_file_size_fmt'] = format_bytes(r.get('script_file_size', 0))

    return jsonify({'assessments': results, 'total': len(results)})
