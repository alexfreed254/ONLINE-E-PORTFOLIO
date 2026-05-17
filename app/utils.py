"""
Shared utility helpers used across blueprints.
"""
import os
import uuid
import csv
import io
from datetime import datetime
from flask import request
from flask_login import current_user
from app.db import get_db

ALLOWED_PDF  = {'pdf'}
ALLOWED_MEDIA = {'jpg', 'jpeg', 'png', 'gif', 'mp4', 'mov', 'avi', 'mkv', 'webm'}

STORAGE_BUCKET_SCRIPTS  = 'assessment-scripts'
STORAGE_BUCKET_EVIDENCE = 'assessment-evidence'


# ─────────────────────────────────────────────────────────────
# FILE HELPERS
# ─────────────────────────────────────────────────────────────

def allowed_pdf(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PDF


def allowed_media(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_MEDIA


def format_bytes(size: int) -> str:
    if not size:
        return '0 Bytes'
    for unit in ['Bytes', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f'{size:.2f} {unit}'
        size /= 1024
    return f'{size:.2f} TB'


def secure_unique_filename(original: str) -> str:
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    return f'{uuid.uuid4().hex}.{ext}'


# ─────────────────────────────────────────────────────────────
# SUPABASE STORAGE UPLOAD
# ─────────────────────────────────────────────────────────────

def get_storage_public_url(bucket: str, path: str) -> str:
    """
    Build the public URL for a file already stored in Supabase Storage.
    Pattern: {SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}
    """
    if not path:
        return ''
    supabase_url = os.getenv('SUPABASE_URL', '').rstrip('/')
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{path}"


def upload_to_storage(bucket: str, path: str, file_bytes: bytes, content_type: str) -> str:
    """Upload bytes to Supabase Storage and return the public URL."""
    db = get_db()
    db.storage.from_(bucket).upload(
        path,
        file_bytes,
        {'content-type': content_type, 'upsert': 'true'}
    )
    return get_storage_public_url(bucket, path)


def delete_from_storage(bucket: str, path: str):
    try:
        db = get_db()
        db.storage.from_(bucket).remove([path])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# SYSTEM LOGGING
# ─────────────────────────────────────────────────────────────

def log_action(action: str, entity: str = None, entity_id: str = None, detail: str = None):
    try:
        db = get_db()
        db.table('system_logs').insert({
            'user_id':    str(current_user.id) if current_user and current_user.is_authenticated else None,
            'action':     action,
            'entity':     entity,
            'entity_id':  str(entity_id) if entity_id else None,
            'detail':     detail,
            'ip_address': request.remote_addr,
        }).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# STATUS DETECTION  (mirrors Google Apps Script logic)
# ─────────────────────────────────────────────────────────────

def get_file_status(filename: str) -> str:
    lower = filename.lower()
    if 'approved by' in lower:
        return 'approved'
    if 'rejected by' in lower or 'rejected' in lower:
        return 'rejected'
    return 'pending'


# ─────────────────────────────────────────────────────────────
# ASSESSMENT FILENAME BUILDER
# ─────────────────────────────────────────────────────────────

def build_assessment_filename(data: dict) -> str:
    """
    Pattern: ADMNO-UNIT-CYCLEn-TERMn-YEAR-TYPE-ASSESSMENTn.pdf
    Mirrors the Google Apps Script uploadFile() naming convention.
    """
    unit = data['unit_name'].replace(' ', '_').upper()
    return (
        f"{data['admission_no']}-{unit}"
        f"-CYCLE{data['cycle']}"
        f"-TERM{data['term']}"
        f"-{data['year']}"
        f"-{data['assessment_type'].upper()}"
        f"-{data['assessment_no']}.pdf"
    )


# ─────────────────────────────────────────────────────────────
# CLASSES & UNITS DATA  (ported from getClassesAndUnits())
# ─────────────────────────────────────────────────────────────

CLASSES_AND_UNITS = {
    'BME L6 JAN 2026':  ['REFRIGIRATION &A/C', 'HUMAN ANATOMY', 'MATHS', 'WORK ETHICS', 'MECHANICAL SCIENCE'],
    'BME SEPT 2025':    ['ELEC PRINCIPLES', 'DIGITAL LITERACY', 'MATHEMATICS', 'COMMUNICATION SKILLS', 'HOSPITAL PLANT & SERVICES', 'DENTAL EQUIPMENT'],
    'CEI L5 1A MAY 2024': ['BREAKDOWN MAINT', 'WORKSHOP TECH', 'TESTING OF ELEC INST', 'ENVIRONMENTAL LIT', 'EMPLOYABILITY SKILLS', 'EP', 'MAINT ELEC INST', 'ENTREPRENUERSHIP SKILLS'],
    'CEI L5 1B MAY 2024': ['BREAKDOWN MAINT', 'WORKSHOP TECH', 'TESTING OF ELEC INST', 'ENVIRONMENTAL LIT', 'EMPLOYABILITY SKILLS', 'EP', 'MAINT ELEC INST', 'ENTREPRENUERSHIP SKILLS'],
    'CEI L5 1C MAY 2024': ['BREAKDOWN MAINT', 'WORKSHOP TECH', 'TESTING OF ELEC INST', 'ENVIRONMENTAL LIT', 'EMPLOYABILITY SKILLS', 'EP', 'MAINT ELEC INST', 'ENTREPRENUERSHIP SKILLS'],
    'CEI L5 1D MAY 2024': ['BREAKDOWN MAINT', 'WORKSHOP TECH', 'TESTING OF ELEC INST', 'ENVIRONMENTAL LIT', 'EMPLOYABILITY SKILLS', 'EP', 'MAINT ELEC INST', 'ENTREPRENUERSHIP SKILLS'],
    'DEE L6 1A SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1B SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1C SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1D SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1E SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1F SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1G SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DEE L6 1H SEPT 2023': ['AUTOMATION OF ELECTRICAL MACHINES', 'ELECTRICAL EQUIPMENT SYSTEM MANAGEMENT', 'ENTREPRENUERSHIP SKILLS', 'ELEC PROJECT MNGT', 'SECURITY SYSTEM INST'],
    'DTEN L6 1A SEPT 2023': ['INSTAL RADAR', 'INSTAL BROADCASTING MONITOR', 'INSTALLATION OF WIFI', 'INSTALLATION OF TELECOMMUNICATION', 'MAINTENANCE OF TELECOMMUNICATION', 'TELECOM PROJ MNGT', 'ENVIRONMENTAL LIT', 'ENTREPRENUERSHIP SKILLS', 'TV & RADIO SIGNAL BROADCAST'],
    'DTEN L6 1B SEPT 2023': ['INSTAL RADAR', 'INSTAL BROADCASTING MONITOR', 'INSTALLATION OF WIFI', 'INSTALLATION OF TELECOMMUNICATION', 'MAINTENANCE OF TELECOMMUNICATION', 'TELECOM PROJ MNGT', 'ENVIRONMENTAL LIT', 'ENTREPRENUERSHIP SKILLS', 'TV & RADIO SIGNAL BROADCAST'],
    'EEN L6 1A JAN 2026':    ['TRUNKING SYSTEM INST', 'PVC SHEATHED', 'CONDUIT SYSTEM INST'],
    'EEN L6 DUAL SEPT 2024': ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1A SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1B SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1C SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1D SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1E SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1F SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1G SEPT 2024':   ['POWER LINES', 'Workshop Technology', 'POWER GENERATION', 'Electrical Principles', 'AUTO ELEC MACHINES', 'ELEC MACHINE INSTL', 'SECURITY SYSTEMS INST', 'EP Skills', 'MATHEMATICS'],
    'EEN_L6 1A SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'Bell and Alarm Installation'],
    'EEN_L6 1B SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'Bell and Alarm Installation'],
    'EEN_L6 1C SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EEN_L6 1D SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EEN_L6 1E SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EEN_L6 1F SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EEN_L6 1G SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EEN_L6 1H SEPT 2025':   ['ELEC MACHINE WINDING', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EET L5 1A JAN 2026':   ['PVC SHEATHED', 'TRUNKING SYTEM INST', 'Conduit System Installation'],
    'EET_L5 1A SEPT 2025':  ['Electrical Machine Winding', 'Solar PV Systems', 'BELL & ALARM INST'],
    'EET_L5 1B SEPT 2025':  ['Electrical Machine Winding', 'Solar PV Systems', 'Bell and Alarm Installation'],
    'EET L5 1C SEPT 2025':  ['Electrical Machine Winding', 'Solar PV Systems', 'Bell and Alarm Installation'],
    'EET_L5 1D SEPT 2025':  ['ELEC MACHINE WINDING', 'SOLAR PV SYSTEMS', 'BELL & ALARM INST'],
    'EIN L4 1A JAN 2026':   ['PVC SHEATHED', 'TRUNKING SYTEM INST', 'Conduit System Installation'],
    'EIN L5 1A MAY 2025':   ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1B MAY 2025':   ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1C MAY 2025':   ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1A SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1B SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1C SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1D SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1E SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'EIN_L5 1F SEPT 2024':  ['Maintain Elec Inst', 'Electrical Principles', 'Workshop Technology', 'Testing of Elec Instl', 'MATHEMATICS', 'EP Skills'],
    'TEL_L6 1A SEPT 2024':  ['Instal Base Transmission', 'Instal Satelite Signal Trans', 'Electrical Pinciples', 'Mathematics', 'Workshop Technology', 'Communication Equipments', 'Telephone Networks', 'Fibre Optic cables', 'Inside Plant Networks'],
    'TEL L6 1A SEPT 2025':  ['Instal Base Transmission', 'Instal Satelite Signal Trans', 'Electrical Pinciples', 'Mathematics', 'Workshop Technology', 'Communication Equipments', 'Telephone Networks', 'Fibre Optic cables', 'Inside Plant Networks'],
}

# ─────────────────────────────────────────────────────────────
# UNIT ASSESSMENT REPORT GENERATION
# ─────────────────────────────────────────────────────────────

def generate_unit_report_csv(unit_id: str, class_id: str = None, department_id: str = None) -> str:
    """
    Generate a CSV report for a unit showing trainees and their assessment uploads.
    Columns: Admission No, Full Name, Practical, Oral, Theory
    Each assessment type shows YES if >= 3 evidence files, blank otherwise.
    """
    db = get_db()
    
    try:
        # Get unit name
        unit = db.table('units').select('name').eq('id', unit_id).single().execute().data
        unit_name = unit['name'] if unit else 'Unit'
        
        # Build query for assessments
        q = (db.table('assessments')
             .select('*, users!assessments_trainee_id_fkey(admission_no, full_name)')
             .eq('unit_id', unit_id))
        
        if class_id:
            q = q.eq('class_id', class_id)
        
        assessments = q.execute().data or []
        
        # Filter by department if provided
        if department_id:
            user_ids = [a['trainee_id'] for a in assessments]
            if user_ids:
                dept_users = db.table('users').select('id').eq('department_id', department_id).execute().data or []
                dept_user_ids = {u['id'] for u in dept_users}
                assessments = [a for a in assessments if a['trainee_id'] in dept_user_ids]
        
        # Count evidence per trainee per assessment type
        trainee_data = {}
        for a in assessments:
            trainee_id = a['trainee_id']
            admission_no = a['users']['admission_no'] if a.get('users') else ''
            full_name = a['users']['full_name'] if a.get('users') else ''
            assessment_type = a.get('assessment_type', '').lower()
            
            if trainee_id not in trainee_data:
                trainee_data[trainee_id] = {
                    'admission_no': admission_no,
                    'full_name': full_name,
                    'practical': '',
                    'oral': '',
                    'theory': '',
                }
            
            # Count evidence for this assessment
            evidence_count = len(db.table('evidence').select('id').eq('assessment_id', a['id']).execute().data or [])
            
            # Map to assessment type
            if assessment_type in ['practical', 'practicals', 'prac']:
                if evidence_count >= 3:
                    trainee_data[trainee_id]['practical'] = 'YES'
            elif assessment_type in ['oral', 'orals']:
                if evidence_count >= 3:
                    trainee_data[trainee_id]['oral'] = 'YES'
            elif assessment_type in ['theory', 'theories', 'theo']:
                if evidence_count >= 3:
                    trainee_data[trainee_id]['theory'] = 'YES'
        
        # Generate CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['Admission No', 'Full Name', 'Practical', 'Oral', 'Theory'])
        writer.writeheader()
        
        # Sort by admission number
        for trainee_id in sorted(trainee_data.keys(), key=lambda t: trainee_data[t]['admission_no']):
            data = trainee_data[trainee_id]
            writer.writerow({
                'Admission No': data['admission_no'],
                'Full Name': data['full_name'],
                'Practical': data['practical'],
                'Oral': data['oral'],
                'Theory': data['theory'],
            })
        
        return output.getvalue()
    except Exception as e:
        return f"Error generating report: {str(e)}"

