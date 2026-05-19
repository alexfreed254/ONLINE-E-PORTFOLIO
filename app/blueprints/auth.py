from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import User
from app.auth_service import authenticate_staff
from app.db import get_db
from app.utils import log_action
from datetime import datetime
import secrets
import string
import re

auth_bp = Blueprint('auth', __name__)

STAFF_ROLES = ('super_admin', 'dept_admin', 'trainer')


def _gen_temp_pw(length=10):
    chars = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(chars) for _ in range(length))


def _clean_name(value: str) -> str:
    return ' '.join((value or '').strip().lower().split())


def _clean_mobile_number(value: str) -> str:
    value = (value or '').strip()
    if value.startswith('+'):
        return '+' + re.sub(r'\D', '', value[1:])
    return re.sub(r'\D', '', value)


@auth_bp.before_app_request
def enforce_trainee_password_change():
    if not current_user.is_authenticated:
        return None
    if current_user.role != 'trainee' or not getattr(current_user, 'must_change_password', False):
        return None
    allowed = {'auth.change_password', 'auth.logout', 'static'}
    if request.endpoint not in allowed:
        flash('Update your temporary password before continuing.', 'warning')
        return redirect(url_for('auth.change_password'))
    return None


# ─────────────────────────────────────────────────────────────
# INDEX
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))

    if request.method == 'POST':
        login_type = request.form.get('login_type', 'staff')
        password   = request.form.get('password', '')
        user       = None

        if login_type == 'trainee':
            adm_no = request.form.get('admission_no', '').strip()
            if not adm_no or not adm_no.isdigit() or len(adm_no) != 5:
                flash('Admission number must be exactly 5 digits.', 'danger')
                return render_template('auth/login.html', active_tab='trainee')
            user = User.get_by_admission_no(adm_no)
            if not user or not check_password_hash(user.password_hash or '', password):
                flash('Invalid admission number or password.', 'danger')
                return render_template('auth/login.html', active_tab='trainee')
        else:
            email = request.form.get('email', '').strip().lower()
            if not email:
                flash('Please enter your email address.', 'danger')
                return render_template('auth/login.html', active_tab='staff')

            # Use authenticate_staff which handles both Supabase Auth
            # (users with auth_user_id) and legacy password_hash fallback
            user = authenticate_staff(email, password)
            if not user:
                flash('Invalid email or password.', 'danger')
                return render_template('auth/login.html', active_tab='staff')
            if user.role == 'trainee':
                flash('Trainees must use the Trainee tab with their admission number.', 'warning')
                return render_template('auth/login.html', active_tab='trainee')

        if not user.is_active:
            flash('Your account has been deactivated. Contact your administrator.', 'danger')
            return render_template('auth/login.html',
                                   active_tab='trainee' if login_type == 'trainee' else 'staff')

        login_user(user, remember=True)
        try:
            get_db().table('users').update(
                {'last_login': datetime.utcnow().isoformat()}
            ).eq('id', user.id).execute()
        except Exception:
            pass

        log_action('LOGIN', 'user', user.id, f'{user.full_name} logged in')
        flash(f'Welcome back, {user.full_name}!', 'success')
        if user.role == 'trainee' and getattr(user, 'must_change_password', False):
            flash('You are using a temporary password. Please set your own password now.', 'warning')
            return redirect(url_for('auth.change_password'))
        return redirect(url_for('auth.dashboard_redirect'))

    active_tab = 'trainee' if request.args.get('tab') == 'trainee' else 'staff'
    return render_template('auth/login.html', active_tab=active_tab)


# ─────────────────────────────────────────────────────────────
# TRAINEE SELF-REGISTRATION
# Trainee enters their admission number + full name (must match
# what admin pre-loaded). If matched and not already activated,
# the system issues a temporary password for first login.
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))

    if request.method == 'POST':
        adm_no    = request.form.get('admission_no', '').strip()
        full_name = _clean_name(request.form.get('full_name', ''))
        mobile_number = _clean_mobile_number(request.form.get('mobile_number', ''))

        # Basic validation
        if not adm_no or not adm_no.isdigit() or len(adm_no) != 5:
            flash('Admission number must be exactly 5 digits.', 'danger')
            return render_template('auth/register.html')
        if not full_name:
            flash('Full name is required.', 'danger')
            return render_template('auth/register.html')
        if not mobile_number or len(re.sub(r'\D', '', mobile_number)) < 10:
            flash('Enter a valid mobile number.', 'danger')
            return render_template('auth/register.html')

        db = get_db()

        # Look up the pre-loaded trainee record
        resp = (db.table('users')
                .select('*')
                .eq('admission_no', adm_no)
                .eq('role', 'trainee')
                .execute())
        trainee_row = resp.data[0] if resp.data else None

        if not trainee_row:
            flash('No trainee found with that admission number. '
                  'Contact your Department Admin to register you first.', 'danger')
            return render_template('auth/register.html')

        # Name must match (case-insensitive, strip spaces)
        stored_name = _clean_name(trainee_row['full_name'])
        if stored_name != full_name:
            flash('Full name does not match our records. '
                  'Enter your name exactly as registered by your admin.', 'danger')
            return render_template('auth/register.html')

        if not trainee_row.get('is_active', True):
            flash('Your account has been deactivated. Contact your administrator.', 'danger')
            return render_template('auth/register.html')

        if trainee_row.get('password_hash') and not trainee_row.get('must_change_password', False):
            flash('This trainee account is already activated. Log in with your admission number and password.', 'warning')
            return redirect(url_for('auth.login') + '?tab=trainee')

        temp_pw = _gen_temp_pw()
        db.table('users').update({
            'password_hash': generate_password_hash(temp_pw),
            'must_change_password': True,
            'mobile_number': mobile_number,
            'is_active': True,
        }).eq('id', trainee_row['id']).execute()

        log_action('TRAINEE_REGISTER', 'user', trainee_row['id'],
                   f'{trainee_row["full_name"]} ({adm_no}) received temporary password')

        flash(f'Account verified. Temporary password: {temp_pw}  Use it to log in, then change it immediately.', 'success')
        return render_template('auth/register.html', issued_temp_password=temp_pw, issued_admission_no=adm_no)

    return render_template('auth/register.html')


# ─────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    log_action('LOGOUT', 'user', current_user.id)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────
# DASHBOARD REDIRECT
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/dashboard')
@login_required
def dashboard_redirect():
    role_map = {
        'super_admin': 'super_admin.dashboard',
        'dept_admin':  'dept_admin.dashboard',
        'trainer':     'trainer.dashboard',
        'trainee':     'trainee.dashboard',
    }
    target = role_map.get(current_user.role)
    if target:
        return redirect(url_for(target))
    flash('Unknown role. Contact administrator.', 'danger')
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────
# CHANGE PASSWORD
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not check_password_hash(current_user.password_hash or '', current_pw):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')
        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return render_template('auth/change_password.html')
        if new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/change_password.html')

        get_db().table('users').update(
            {
                'password_hash': generate_password_hash(new_pw),
                'must_change_password': False,
            }
        ).eq('id', current_user.id).execute()
        log_action('CHANGE_PASSWORD', 'user', current_user.id)
        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.dashboard_redirect'))

    return render_template('auth/change_password.html')
