"""Sidebar stats injected into every authenticated admin/trainer template."""
from flask_login import current_user


def get_sidebar_stats():
    if not current_user.is_authenticated:
        return None
    if current_user.role not in ('super_admin', 'dept_admin', 'trainer'):
        return None

    try:
        from app.db import get_db
        db = get_db()
    except Exception:
        return None

    role = current_user.role
    dep_id = str(current_user.department_id) if current_user.department_id else None

    try:
        if role == 'super_admin':
            all_assess = db.table('assessments').select('status').execute().data or []
            return {
                'kind': 'super_admin',
                'users': len(db.table('users').select('id').execute().data or []),
                'pending': sum(1 for a in all_assess if a['status'] == 'pending'),
                'approved': sum(1 for a in all_assess if a['status'] == 'approved'),
            }

        if role == 'dept_admin':
            q_classes = db.table('classes').select('id')
            if dep_id:
                q_classes = q_classes.eq('department_id', dep_id)
            classes_n = len(q_classes.execute().data or [])

            q_trainers = db.table('users').select('id').eq('role', 'trainer')
            q_trainees = db.table('users').select('id').eq('role', 'trainee')
            if dep_id:
                q_trainers = q_trainers.eq('department_id', dep_id)
                q_trainees = q_trainees.eq('department_id', dep_id)
            return {
                'kind': 'dept_admin',
                'classes': classes_n,
                'trainers': len(q_trainers.execute().data or []),
                'trainees': len(q_trainees.execute().data or []),
            }

        if role == 'trainer':
            q = db.table('assessments').select('status')
            if dep_id:
                class_ids = [
                    c['id'] for c in
                    db.table('classes').select('id').eq('department_id', dep_id).execute().data or []
                ]
                if class_ids:
                    q = q.in_('class_id', class_ids)
            all_a = q.execute().data or []
            return {
                'kind': 'trainer',
                'total': len(all_a),
                'pending': sum(1 for a in all_a if a['status'] == 'pending'),
                'approved': sum(1 for a in all_a if a['status'] == 'approved'),
            }
    except Exception:
        return None

    return None
