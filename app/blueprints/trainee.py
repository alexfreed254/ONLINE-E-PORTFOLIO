from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from app.db import get_db
from app.utils import (
    log_action, format_bytes, allowed_pdf, allowed_media,
    upload_to_storage, delete_from_storage,
    STORAGE_BUCKET_SCRIPTS, STORAGE_BUCKET_EVIDENCE,
    build_assessment_filename, secure_unique_filename
)
import uuid

trainee_bp = Blueprint('trainee', __name__)


def trainee_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'trainee':
            flash('Trainee access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/dashboard')
@login_required
@trainee_required
def dashboard():
    db    = get_db()
    tid   = str(current_user.id)
    stats = {}
    try:
        all_a = db.table('assessments').select('status').eq('trainee_id', tid).execute().data or []
        stats['total']    = len(all_a)
        stats['pending']  = sum(1 for a in all_a if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_a if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_a if a['status'] == 'rejected')

        recent = (db.table('assessments')
                  .select('*, units(name), classes(name)')
                  .eq('trainee_id', tid)
                  .order('uploaded_at', desc=True)
                  .limit(10)
                  .execute().data or [])
        for r in recent:
            r['script_file_size_fmt'] = format_bytes(r.get('script_file_size', 0))
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        recent = []

    return render_template('trainee/dashboard.html', stats=stats, recent=recent)


# ─────────────────────────────────────────────────────────────
# UPLOAD ASSESSMENT (PDF script)
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@trainee_required
def upload():
    db = get_db()

    # Get enrolled classes
    enrollments = (db.table('enrollments')
                   .select('classes(id, name, course_id)')
                   .eq('trainee_id', str(current_user.id))
                   .execute().data or [])
    classes = [e['classes'] for e in enrollments if e.get('classes')]

    if request.method == 'POST':
        class_id    = request.form.get('class_id', '').strip()
        unit_id     = request.form.get('unit_id', '').strip()
        term        = request.form.get('term', '').strip()
        cycle       = request.form.get('cycle', '').strip()
        year        = request.form.get('year', '').strip()
        assess_type = request.form.get('assessment_type', '').strip().upper()
        assess_no   = request.form.get('assessment_no', '').strip()
        pdf_file    = request.files.get('script_file')

        # Validation
        errors = []
        if not class_id:  errors.append('Class is required.')
        if not unit_id:   errors.append('Unit is required.')
        if not term:      errors.append('Term is required.')
        if not cycle:     errors.append('Cycle is required.')
        if not year:      errors.append('Year is required.')
        if not assess_type: errors.append('Assessment type is required.')
        if not assess_no:   errors.append('Assessment number is required.')
        if not pdf_file or pdf_file.filename == '':
            errors.append('Please select a PDF file.')
        elif not allowed_pdf(pdf_file.filename):
            errors.append('Only PDF files are accepted.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return redirect(url_for('trainee.upload'))

        # Get unit name for filename
        unit_row = db.table('units').select('name').eq('id', unit_id).single().execute().data
        unit_name = unit_row['name'] if unit_row else 'UNIT'

        filename = build_assessment_filename({
            'admission_no':    current_user.admission_no,
            'unit_name':       unit_name,
            'cycle':           cycle,
            'term':            term,
            'year':            year,
            'assessment_type': assess_type,
            'assessment_no':   assess_no,
        })

        storage_path = f"{current_user.admission_no}/{class_id}/{unit_id}/{filename}"
        file_bytes   = pdf_file.read()
        file_size    = len(file_bytes)

        try:
            upload_to_storage(STORAGE_BUCKET_SCRIPTS, storage_path, file_bytes, 'application/pdf')
        except Exception as e:
            flash(f'File upload failed: {e}', 'danger')
            return redirect(url_for('trainee.upload'))

        # Save to DB
        try:
            db.table('assessments').insert({
                'trainee_id':       str(current_user.id),
                'class_id':         class_id,
                'unit_id':          unit_id,
                'assessment_type':  assess_type,
                'assessment_no':    int(assess_no),
                'term':             int(term),
                'cycle':            int(cycle),
                'year':             int(year),
                'script_file_path': storage_path,
                'script_file_name': filename,
                'script_file_size': file_size,
                'status':           'pending',
            }).execute()
            log_action('UPLOAD_ASSESSMENT', 'assessment', None,
                       f'{current_user.admission_no} uploaded {filename}')
            flash('Assessment uploaded successfully! Awaiting trainer review.', 'success')
        except Exception as e:
            delete_from_storage(STORAGE_BUCKET_SCRIPTS, storage_path)
            flash(f'Database error: {e}', 'danger')

        return redirect(url_for('trainee.my_files'))

    # GET — load units for first enrolled class
    units = []
    if classes:
        first_class_id = classes[0]['id']
        units_raw = (db.table('class_units')
                     .select('units(id, name)')
                     .eq('class_id', first_class_id)
                     .execute().data or [])
        units = [r['units'] for r in units_raw if r.get('units')]

    current_year = datetime.utcnow().year
    years = list(range(2020, current_year + 2))
    return render_template('trainee/upload.html', classes=classes, units=units, years=years)


# ─────────────────────────────────────────────────────────────
# API: get units for a class
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/api/units/<class_id>')
@login_required
@trainee_required
def api_units(class_id):
    db = get_db()
    rows = (db.table('class_units')
            .select('units(id, name)')
            .eq('class_id', class_id)
            .execute().data or [])
    units = [r['units'] for r in rows if r.get('units')]
    return jsonify({'units': units})


# ─────────────────────────────────────────────────────────────
# MY FILES
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/my-files')
@login_required
@trainee_required
def my_files():
    db     = get_db()
    tid    = str(current_user.id)
    status = request.args.get('status', '')

    q = (db.table('assessments')
         .select('*, units(name), classes(name)')
         .eq('trainee_id', tid))
    if status:
        q = q.eq('status', status)
    assessments = q.order('uploaded_at', desc=True).execute().data or []

    for a in assessments:
        a['script_file_size_fmt'] = format_bytes(a.get('script_file_size', 0))
        # Get evidence count
        ev = db.table('evidence').select('id').eq('assessment_id', a['id']).execute().data or []
        a['evidence_count'] = len(ev)

    counts = {
        'total':    len(assessments),
        'pending':  sum(1 for a in assessments if a['status'] == 'pending'),
        'approved': sum(1 for a in assessments if a['status'] == 'approved'),
        'rejected': sum(1 for a in assessments if a['status'] == 'rejected'),
    }
    return render_template('trainee/my_files.html',
                           assessments=assessments, counts=counts, status_filter=status)


# ─────────────────────────────────────────────────────────────
# DELETE REJECTED ASSESSMENT
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/assessment/<assessment_id>/delete', methods=['POST'])
@login_required
@trainee_required
def delete_assessment(assessment_id):
    db = get_db()
    a  = (db.table('assessments')
          .select('*')
          .eq('id', assessment_id)
          .eq('trainee_id', str(current_user.id))
          .single()
          .execute().data)

    if not a:
        flash('Assessment not found or access denied.', 'danger')
        return redirect(url_for('trainee.my_files'))

    if a['status'] != 'rejected':
        flash('Only rejected assessments can be deleted.', 'danger')
        return redirect(url_for('trainee.my_files'))

    # Delete PDF from storage
    if a.get('script_file_path'):
        delete_from_storage(STORAGE_BUCKET_SCRIPTS, a['script_file_path'])

    # Delete evidence
    evs = db.table('evidence').select('file_path').eq('assessment_id', assessment_id).execute().data or []
    for ev in evs:
        delete_from_storage(STORAGE_BUCKET_EVIDENCE, ev['file_path'])

    db.table('assessments').delete().eq('id', assessment_id).execute()
    log_action('DELETE_ASSESSMENT', 'assessment', assessment_id,
               f'{current_user.admission_no} deleted rejected assessment')
    flash('Rejected assessment deleted. You can now re-upload the correct scan.', 'success')
    return redirect(url_for('trainee.my_files'))


# ─────────────────────────────────────────────────────────────
# UPLOAD EVIDENCE (photo/video linked to an assessment)
# ─────────────────────────────────────────────────────────────
@trainee_bp.route('/assessment/<assessment_id>/evidence', methods=['GET', 'POST'])
@login_required
@trainee_required
def upload_evidence(assessment_id):
    db = get_db()
    a  = (db.table('assessments')
          .select('*, units(name), classes(name)')
          .eq('id', assessment_id)
          .eq('trainee_id', str(current_user.id))
          .single()
          .execute().data)

    if not a:
        flash('Assessment not found.', 'danger')
        return redirect(url_for('trainee.my_files'))

    if request.method == 'POST':
        media_file = request.files.get('evidence_file')
        caption    = request.form.get('caption', '').strip()

        if not media_file or media_file.filename == '':
            flash('Please select a file.', 'danger')
            return redirect(url_for('trainee.upload_evidence', assessment_id=assessment_id))

        if not allowed_media(media_file.filename):
            flash('Allowed formats: JPG, PNG, GIF, MP4, MOV, AVI, MKV, WEBM.', 'danger')
            return redirect(url_for('trainee.upload_evidence', assessment_id=assessment_id))

        ext       = media_file.filename.rsplit('.', 1)[-1].lower()
        file_type = 'video' if ext in ('mp4', 'mov', 'avi', 'mkv', 'webm') else 'photo'
        unique_fn = secure_unique_filename(media_file.filename)
        storage_path = f"evidence/{current_user.admission_no}/{assessment_id}/{unique_fn}"
        file_bytes   = media_file.read()
        file_size    = len(file_bytes)
        content_type = f"{'video' if file_type == 'video' else 'image'}/{ext}"

        try:
            upload_to_storage(STORAGE_BUCKET_EVIDENCE, storage_path, file_bytes, content_type)
        except Exception as e:
            flash(f'Upload failed: {e}', 'danger')
            return redirect(url_for('trainee.upload_evidence', assessment_id=assessment_id))

        try:
            db.table('evidence').insert({
                'assessment_id': assessment_id,
                'trainee_id':    str(current_user.id),
                'file_path':     storage_path,
                'file_name':     media_file.filename,
                'file_type':     file_type,
                'file_size':     file_size,
                'caption':       caption or None,
            }).execute()
            log_action('UPLOAD_EVIDENCE', 'evidence', assessment_id,
                       f'{file_type} evidence for assessment {assessment_id}')
            flash(f'{file_type.capitalize()} evidence uploaded successfully.', 'success')
        except Exception as e:
            delete_from_storage(STORAGE_BUCKET_EVIDENCE, storage_path)
            flash(f'Database error: {e}', 'danger')

        return redirect(url_for('trainee.upload_evidence', assessment_id=assessment_id))

    # GET
    evidence = (db.table('evidence')
                .select('*')
                .eq('assessment_id', assessment_id)
                .order('uploaded_at')
                .execute().data or [])
    for ev in evidence:
        ev['file_size_fmt'] = format_bytes(ev.get('file_size', 0))

    return render_template('trainee/upload_evidence.html',
                           assessment=a, evidence=evidence, format_bytes=format_bytes)


@trainee_bp.route('/evidence/<evidence_id>/delete', methods=['POST'])
@login_required
@trainee_required
def delete_evidence(evidence_id):
    db = get_db()
    ev = (db.table('evidence')
          .select('*')
          .eq('id', evidence_id)
          .eq('trainee_id', str(current_user.id))
          .single()
          .execute().data)

    if not ev:
        flash('Evidence not found.', 'danger')
        return redirect(url_for('trainee.my_files'))

    delete_from_storage(STORAGE_BUCKET_EVIDENCE, ev['file_path'])
    db.table('evidence').delete().eq('id', evidence_id).execute()
    log_action('DELETE_EVIDENCE', 'evidence', evidence_id)
    flash('Evidence deleted.', 'success')
    assessment_id = ev.get('assessment_id')
    return redirect(url_for('trainee.upload_evidence', assessment_id=assessment_id))
