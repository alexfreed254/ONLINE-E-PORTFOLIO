from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import User
from app.db import get_db
from app.utils import log_action
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard_redirect'))

    if request.method == 'POST':
        login_type = request.form.get('login_type', 'staff')  # 'staff' or 'trainee'
        password   = request.form.get('password', '')
        user       = None

        if login_type == 'trainee':
            # Trainees log in with admission number
            adm_no = request.form.get('admission_no', '').strip()
            if not adm_no:
                flash('Please enter your admission number.', 'danger')
                return render_template('auth/login.html', active_tab='trainee')
            if not adm_no.isdigit() or len(adm_no) != 5:
                flash('Admission number must be exactly 5 digits.', 'danger')
                return render_template('auth/login.html', active_tab='trainee')
            user = User.get_by_admission_no(adm_no)
            if not user or not check_password_hash(user.password_hash, password):
                flash('Invalid admission number or password.', 'danger')
                return render_template('auth/login.html', active_tab='trainee')
            if user.role != 'trainee':
                flash('Use Staff Login with your email address.', 'warning')
                return render_template('auth/login.html', active_tab='staff')
        else:
            # Staff (super_admin, dept_admin, trainer) log in with email
            email = request.form.get('email', '').strip().lower()
            if not email:
                flash('Please enter your email address.', 'danger')
                return render_template('auth/login.html', active_tab='staff')
            user = User.get_by_email(email)
            if not user or not check_password_hash(user.password_hash, password):
                flash('Invalid email or password.', 'danger')
                return render_template('auth/login.html', active_tab='staff')
            if user.role not in ('super_admin', 'dept_admin', 'trainer'):
                flash('Staff login is for Super Admins, Department Admins and Trainers only. Use the Trainee tab.', 'warning')
                return render_template('auth/login.html', active_tab='trainee')

        if not user.is_active:
            flash('Your account has been deactivated. Contact your administrator.', 'danger')
            tab = 'trainee' if login_type == 'trainee' else 'staff'
            return render_template('auth/login.html', active_tab=tab)

        login_user(user, remember=True)

        # Update last_login timestamp
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


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('LOGOUT', 'user', current_user.id)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


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


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not check_password_hash(current_user.password_hash, current_pw):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')

        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return render_template('auth/change_password.html')

        if new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/change_password.html')

        hashed = generate_password_hash(new_pw)
        get_db().table('users').update({'password_hash': hashed}).eq('id', current_user.id).execute()
        log_action('CHANGE_PASSWORD', 'user', current_user.id)
        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.dashboard_redirect'))

    return render_template('auth/change_password.html')
