from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import User
from app.db import get_db
from app.utils import log_action
from datetime import datetime
import secrets
import string

auth_bp = Blueprint('auth', __name__)

STAFF_ROLES = ('super_admin', 'dept_admin', 'trainer')


def _gen_temp_pw(length=10):
    chars = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(chars) for _ in range(length))


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
            user = User.get_by_email(email)
            if not user or not check_password_hash(user.password_hash or '', password):
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
        return redirect(url_for('auth.dashboard_redirect'))

    return render_template('auth/login.html', active_tab='staff')


# ─────────────────────────────────────────────────────────────
# TRAINEE SELF-REGISTRATION
# Trainee enters their admission number + full name (must match
# what admin pre-loaded). If matched and account has no password
# yet (or is a fresh account), they set their own password.
# ─────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))

    if request.method == 'POST':
        adm_no    = request.form.get('admission_no', '').strip()
        full_name = request.form.get('full_name', '').strip().lower()
        temp_pw   = request.form.get('temp_password', '').strip()   # optional
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        # Basic validation
        if not adm_no or not adm_no.isdigit() or len(adm_no) != 5:
            flash('Admission number must be exactly 5 digits.', 'danger')
            return render_template('auth/register.html')
        if not full_name:
            flash('Full name is required.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
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
        stored_name = trainee_row['full_name'].strip().lower()
        if stored_name != full_name:
            flash('Full name does not match our records. '
                  'Enter your name exactly as registered by your admin.', 'danger')
            return render_template('auth/register.html')

        if not trainee_row.get('is_active', True):
            flash('Your account has been deactivated. Contact your administrator.', 'danger')
            return render_template('auth/register.html')

        # If a temporary password was provided, verify it matches
        if temp_pw:
            if not check_password_hash(trainee_row.get('password_hash') or '', temp_pw):
                flash('Temporary password is incorrect. Leave it blank if you do not have one.', 'danger')
                return render_template('auth/register.html')

        # Set the new password (works for both first-time and re-registration)
        db.table('users').update({
            'password_hash': generate_password_hash(password),
            'is_active':     True,
        }).eq('id', trainee_row['id']).execute()

        log_action('TRAINEE_REGISTER', 'user', trainee_row['id'],
                   f'{trainee_row["full_name"]} ({adm_no}) set password')

        flash('Account activated! You can now log in with your admission number and new password.', 'success')
        return redirect(url_for('auth.login') + '?tab=trainee')

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
            {'password_hash': generate_password_hash(new_pw)}
        ).eq('id', current_user.id).execute()
        log_action('CHANGE_PASSWORD', 'user', current_user.id)
        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.dashboard_redirect'))

    return render_template('auth/change_password.html')
