import logging
import os
import secrets
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
    app.config['WTF_CSRF_ENABLED'] = True

    # Configure logging: level controlled by LOG_LEVEL env var (default: INFO)
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        stream=None,  # defaults to stderr
    )

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    csrf.init_app(app)

    # Error handler for file size limit
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return render_template('error_413.html', max_size_mb=16), 413

    return app
