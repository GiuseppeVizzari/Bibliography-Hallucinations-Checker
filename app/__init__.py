from flask import Flask, render_template

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev'  # Change this in production
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    # Error handler for file size limit
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return render_template('error_413.html', max_size_mb=16), 413

    return app
