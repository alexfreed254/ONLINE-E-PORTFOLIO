from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from app.db import get_db
from app.utils import log_action, format_bytes

trainer_bp = Blueprint('trainer', __name__)


def trainer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('trainer', 'dept_admin', 'super_admin'):
            flash('Trainer access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/dashboard')
@login_required
@trainer_required
def dashboard():
    db    = get_db()
    dep_id = str(current_user.department_id) if current_user.department_id else None
    stats  = {}
    try:
        q = db.table('assessments').select('status')
        if dep_id:
            # Filter via class → department
            class_ids = [c['id'] for c in
                         db.table('classes').select('id').eq('department_id', dep_id).execute().data or []]
            if class_ids:
                q = q.in_('class_id', class_ids)
        all_a = q.execute().data or []
        stats['total']    = len(all_a)
        stats['pending']  = sum(1 for a in all_a if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_a if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_a if a['status'] == 'rejected')

        # Recent pending
        q2 = (db.table('assessments')
              .select('*, users!assessments_trainee_id_fkey(full_name, admission_no), units(name), classes(name)')
              .eq('status', 'pending')
              .order('uploaded_at', desc=True)
              .limit(15))
        recent_pending = q2.execute().data or []
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        recent_pending = []

    return render_template('trainer/dashboard.html', stats=stats, recent_pending=recent_pending)


# ─────────────────────────────────────────────────────────────
# BROWSE — Class → Unit → Files (mirrors Google Apps Script)
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

    units_raw = (db.table('class_units')
                 .select('units(id, name)')
                 .eq('class_id', class_id)
                 .execute().data or [])
    units = [r['units'] for r in units_raw if r.get('units')]

    # Count assessments per unit
    for unit in units:
        counts = (db.table('assessments')
                  .select('status')
                  .eq('class_id', class_id)
                  .eq('unit_id', unit['id'])
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

    status_filter = request.args.get('status', '')
    q = (db.table('assessments')
         .select('*, users!assessments_trainee_id_fkey(full_name, admission_no)')
         .eq('class_id', class_id)
         .eq('unit_id', unit_id))
    if status_filter:
        q = q.eq('status', status_filter)
    assessments = q.order('uploaded_at', desc=True).execute().data or []

    # Attach evidence counts
    for a in assessments:
        ev = db.table('evidence').select('id').eq('assessment_id', a['id']).execute().data or []
        a['evidence_count'] = len(ev)
        a['script_file_size_fmt'] = format_bytes(a.get('script_file_size', 0))

    return render_template('trainer/browse_unit.html',
                           cls=cls, unit=unit, assessments=assessments,
                           status_filter=status_filter)


# ─────────────────────────────────────────────────────────────
# ASSESSMENT DETAIL + EVIDENCE
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>')
@login_required
@trainer_required
def assessment_detail(assessment_id):
    db = get_db()
    a  = (db.table('assessments')
          .select('*, users!assessments_trainee_id_fkey(full_name, admission_no, email), units(name), classes(name)')
          .eq('id', assessment_id)
          .single()
          .execute().data)
    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainer.dashboard'))

    evidence = (db.table('evidence')
                .select('*')
                .eq('assessment_id', assessment_id)
                .order('uploaded_at')
                .execute().data or [])

    reviewer = None
    if a.get('reviewed_by'):
        rev = db.table('users').select('full_name').eq('id', a['reviewed_by']).single().execute().data
        reviewer = rev['full_name'] if rev else None

    return render_template('trainer/assessment_detail.html',
                           assessment=a, evidence=evidence, reviewer=reviewer,
                           format_bytes=format_bytes)


# ─────────────────────────────────────────────────────────────
# APPROVE / REJECT
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/assessment/<assessment_id>/approve', methods=['POST'])
@login_required
@trainer_required
def approve_assessment(assessment_id):
    note = request.form.get('note', '').strip()
    from datetime import datetime
    get_db().table('assessments').update({
        'status':      'approved',
        'reviewed_by': str(current_user.id),
        'reviewed_at': datetime.utcnow().isoformat(),
        'review_note': note,
        'updated_at':  datetime.utcnow().isoformat(),
    }).eq('id', assessment_id).execute()
    log_action('APPROVE_ASSESSMENT', 'assessment', assessment_id,
               f'Approved by {current_user.full_name}')
    flash('Assessment approved.', 'success')
    return redirect(request.referrer or url_for('trainer.dashboard'))


@trainer_bp.route('/assessment/<assessment_id>/reject', methods=['POST'])
@login_required
@trainer_required
def reject_assessment(assessment_id):
    note = request.form.get('note', '').strip()
    from datetime import datetime
    get_db().table('assessments').update({
        'status':      'rejected',
        'reviewed_by': str(current_user.id),
        'reviewed_at': datetime.utcnow().isoformat(),
        'review_note': note or 'Rejected by trainer.',
        'updated_at':  datetime.utcnow().isoformat(),
    }).eq('id', assessment_id).execute()
    log_action('REJECT_ASSESSMENT', 'assessment', assessment_id,
               f'Rejected by {current_user.full_name}')
    flash('Assessment rejected.', 'warning')
    return redirect(request.referrer or url_for('trainer.dashboard'))


@trainer_bp.route('/assessment/<assessment_id>/delete', methods=['POST'])
@login_required
@trainer_required
def delete_assessment(assessment_id):
    db = get_db()
    a  = db.table('assessments').select('script_file_path').eq('id', assessment_id).single().execute().data
    if a and a.get('script_file_path'):
        from app.utils import delete_from_storage, STORAGE_BUCKET_SCRIPTS
        delete_from_storage(STORAGE_BUCKET_SCRIPTS, a['script_file_path'])
    # Delete evidence files
    evs = db.table('evidence').select('file_path').eq('assessment_id', assessment_id).execute().data or []
    for ev in evs:
        from app.utils import delete_from_storage, STORAGE_BUCKET_EVIDENCE
        delete_from_storage(STORAGE_BUCKET_EVIDENCE, ev['file_path'])
    db.table('assessments').delete().eq('id', assessment_id).execute()
    log_action('DELETE_ASSESSMENT', 'assessment', assessment_id)
    flash('Assessment deleted.', 'success')
    return redirect(request.referrer or url_for('trainer.dashboard'))


# ─────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────
@trainer_bp.route('/search')
@login_required
@trainer_required
def search():
    db      = get_db()
    dep_id  = str(current_user.department_id) if current_user.department_id else None
    classes = db.table('classes').select('*').order('name').execute().data or []
    units   = db.table('units').select('*').order('name').execute().data or []
    return render_template('trainer/search.html', classes=classes, units=units)


@trainer_bp.route('/search/results')
@login_required
@trainer_required
def search_results():
    db     = get_db()
    adm    = request.args.get('adm', '').strip()
    cls_id = request.args.get('class_id', '').strip()
    unit_id = request.args.get('unit_id', '').strip()
    status = request.args.get('status', '').strip()
    year   = request.args.get('year', '').strip()

    q = db.table('assessments').select(
        '*, users!assessments_trainee_id_fkey(full_name, admission_no), units(name), classes(name)'
    )
    if adm:
        # Join via trainee admission_no
        trainees = db.table('users').select('id').eq('admission_no', adm).execute().data or []
        if trainees:
            q = q.eq('trainee_id', trainees[0]['id'])
        else:
            return jsonify({'assessments': [], 'total': 0})
    if cls_id:
        q = q.eq('class_id', cls_id)
    if unit_id:
        q = q.eq('unit_id', unit_id)
    if status:
        q = q.eq('status', status)
    if year:
        q = q.eq('year', int(year))

    results = q.order('uploaded_at', desc=True).execute().data or []
    for r in results:
        r['script_file_size_fmt'] = format_bytes(r.get('script_file_size', 0))

    return jsonify({'assessments': results, 'total': len(results)})
