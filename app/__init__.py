from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
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

    # Inject `now` and sidebar stats into every template context
    @app.context_processor
    def inject_globals():
        from app.sidebar_context import get_sidebar_stats
        return {
            'now': datetime.utcnow(),
            'sidebar_stats': get_sidebar_stats(),
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

    return app
