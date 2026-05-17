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
    Staff login: Supabase Auth first (if auth_user_id is set),
    then legacy password_hash fallback.
    Returns User profile or None.
    """
    import logging
    log = logging.getLogger(__name__)

    email = email.strip().lower()
    profile = User.get_by_email(email)
    if not profile or profile.role not in STAFF_ROLES:
        return None

    # ── Path 1: Supabase Auth (users linked via auth_user_id) ──
    if profile.auth_user_id:
        try:
            client = get_auth_client()
            result = client.auth.sign_in_with_password({
                'email': email,
                'password': password,
            })
            if result and result.user:
                return profile
            # sign_in returned but no user — wrong password
            return None
        except Exception as exc:
            err = str(exc).lower()
            # If it's clearly an invalid credentials error, reject immediately
            if any(k in err for k in ('invalid', 'credentials', 'wrong', 'incorrect',
                                       'email not confirmed', 'invalid login')):
                log.warning('Supabase Auth rejected login for %s: %s', email, exc)
                return None
            # Otherwise it may be a network/config issue — fall through to legacy hash
            log.warning('Supabase Auth error for %s (%s), trying legacy hash', email, exc)

    # ── Path 2: Legacy password_hash in public.users ──
    if profile.password_hash and check_password_hash(profile.password_hash, password):
        return profile

    return None
