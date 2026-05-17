"""
Flask-Login user model backed by Supabase (no SQLAlchemy).
"""
from flask_login import UserMixin
from app.db import get_db


class User(UserMixin):
    def __init__(self, data: dict):
        self.id            = data['id']
        self.email         = data['email']
        self.full_name     = data['full_name']
        self.role          = data['role']
        self.department_id = data.get('department_id')
        self.admission_no  = data.get('admission_no')
        self.staff_no      = data.get('staff_no')
        self.auth_user_id  = data.get('auth_user_id')
        self._is_active    = data.get('is_active', True)
        self.password_hash = data.get('password_hash') or ''

    def get_id(self):
        return str(self.id)

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_dept_admin(self):
        return self.role == 'dept_admin'

    @property
    def is_trainer(self):
        return self.role == 'trainer'

    @property
    def is_trainee(self):
        return self.role == 'trainee'

    # ── Flask-Login required ──────────────────────────────────
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    # ── Active check ──────────────────────────────────────────
    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value):
        self._is_active = value

    # ── Loader ────────────────────────────────────────────────
    @staticmethod
    def get(user_id: str):
        try:
            db   = get_db()
            resp = db.table('users').select('*').eq('id', user_id).single().execute()
            if resp.data:
                return User(resp.data)
        except Exception:
            pass
        return None

    @staticmethod
    def get_by_email(email: str):
        try:
            db   = get_db()
            resp = db.table('users').select('*').eq('email', email).single().execute()
            if resp.data:
                return User(resp.data)
        except Exception:
            pass
        return None

    @staticmethod
    def get_by_admission_no(admission_no: str):
        """Look up a trainee by their 5-digit admission number."""
        try:
            db   = get_db()
            resp = (db.table('users')
                    .select('*')
                    .eq('admission_no', admission_no)
                    .eq('role', 'trainee')
                    .single()
                    .execute())
            if resp.data:
                return User(resp.data)
        except Exception:
            pass
        return None
