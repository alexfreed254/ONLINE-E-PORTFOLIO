from flask import Flask, jsonify
from flask_login import LoginManager
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import os

load_dotenv()

login_manager = LoginManager()

BASE_DIR = Path(__file__).resolve().parent.parent

def create_app():
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / 'templates'),
        static_folder=str(BASE_DIR / 'static'),
    )
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

    if os.getenv('FLASK_ENV') == 'production':
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # Inject `now`, sidebar stats, and storage URL helper into every template context
    @app.context_processor
    def inject_globals():
        from app.sidebar_context import get_sidebar_stats
        from app.utils import (
            get_storage_public_url,
            STORAGE_BUCKET_SCRIPTS,
            STORAGE_BUCKET_EVIDENCE,
        )
        return {
            'now': datetime.utcnow(),
            'sidebar_stats': get_sidebar_stats(),
            'storage_url': get_storage_public_url,
            'BUCKET_SCRIPTS': STORAGE_BUCKET_SCRIPTS,
            'BUCKET_EVIDENCE': STORAGE_BUCKET_EVIDENCE,
        }

    from app.blueprints.auth        import auth_bp
    from app.blueprints.super_admin import super_admin_bp
    from app.blueprints.dept_admin  import dept_admin_bp
    from app.blueprints.trainer     import trainer_bp
    from app.blueprints.trainee     import trainee_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(super_admin_bp, url_prefix='/super-admin')
    app.register_blueprint(dept_admin_bp,  url_prefix='/dept-admin')
    app.register_blueprint(trainer_bp,     url_prefix='/trainer')
    app.register_blueprint(trainee_bp,     url_prefix='/trainee')

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'}), 200

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.get(user_id)

    return app


# WSGI entry point — used by gunicorn (e.g. Render: gunicorn app:app)
app = create_app()
