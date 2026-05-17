"""
Supabase Authentication for staff (super_admin, dept_admin, trainer).

Trainees continue to use admission number + password_hash in public.users.
"""
from werkzeug.security import check_password_hash
from app.db import get_auth_client, get_db
from app.models import User

STAFF_ROLES = frozenset({'super_admin', 'dept_admin', 'trainer'})


def create_staff_auth_user(email: str, password: str) -> str:
    """Create user in Supabase Auth (auth.users). Returns auth user UUID."""
    db = get_db()
    response = db.auth.admin.create_user({
        'email': email,
        'password': password,
        'email_confirm': True,
    })
    if not response or not response.user:
        raise RuntimeError('Supabase Auth did not return a user.')
    return str(response.user.id)


def update_staff_auth_password(auth_user_id: str, new_password: str) -> None:
    get_db().auth.admin.update_user_by_id(auth_user_id, {'password': new_password})


def delete_staff_auth_user(auth_user_id: str) -> None:
    try:
        get_db().auth.admin.delete_user(auth_user_id)
    except Exception:
        pass


def authenticate_staff(email: str, password: str):
    """
  Staff login: Supabase Auth first, then legacy password_hash fallback.
  Returns User profile or None.
    """
    email = email.strip().lower()
    profile = User.get_by_email(email)
    if not profile or profile.role not in STAFF_ROLES:
        return None

    # Supabase Auth (users created via Authentication → Add user)
    if profile.auth_user_id:
        try:
            client = get_auth_client()
            result = client.auth.sign_in_with_password({
                'email': email,
                'password': password,
            })
            if result and result.user:
                return profile
        except Exception:
            return None

    # Legacy: password stored only in public.users
    if profile.password_hash and check_password_hash(profile.password_hash, password):
        return profile

    return None
