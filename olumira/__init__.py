"""Application construction without schema changes or destructive startup tasks."""
import uuid
from pathlib import Path
from flask import Flask, g, render_template, request, session
from .config import configuration


class OlumiraFlask(Flask):
    def log_exception(self, exc_info):
        # Exception strings can contain SQL parameters or private submitted data.
        self.logger.error('Unhandled request failure: endpoint=%s', request.endpoint)



def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    app = OlumiraFlask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(configuration(config))

    from .extensions import db, migrate
    from . import models
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from werkzeug.exceptions import InternalServerError
    db.init_app(app)
    migrate.init_app(app, db, directory=str(root / 'migrations'))
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            @event.listens_for(db.engine, 'connect')
            def sqlite_foreign_keys(connection, record):
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.close()

    from .routes import dashboard, routines, communication, observations, resources
    for module in (dashboard, routines, communication, observations, resources):
        app.register_blueprint(module.bp)

    @app.before_request
    def load_workspace():
        if request.endpoint in (None, 'static'):
            return
        from services.database import ensure_workspace
        owner_id = session.get('owner_id') or uuid.uuid4().hex
        ensure_workspace(owner_id)
        session['owner_id'] = owner_id
        session.permanent = True
        g.owner_id = owner_id

    messages = {
        400: ('Let’s check that request', 'Some information was missing or could not be accepted. Please go back and try again.'),
        404: ('This page has wandered off', 'We couldn’t find that page or item. You can return to your dashboard to continue.'),
        405: ('That action isn’t available here', 'Please use the page controls to complete this action.'),
        500: ('Something needs a little attention', 'We couldn’t complete your request. Please try again in a moment.'),
    }

    def error_page(error):
        code = getattr(error, 'code', 500)
        if code >= 500:
            # Log only the status and endpoint, never form data, SQL or exception strings.
            app.logger.error('Request failed: status=%s endpoint=%s', code, request.endpoint)
        title, message = messages[code]
        response = error.get_response()
        response.data = render_template('error.html', code=code, heading=title, message=message)
        response.content_type = 'text/html; charset=utf-8'
        return response

    for code in messages:
        app.register_error_handler(code, error_page)
    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        return error_page(InternalServerError())

    from .commands import register_commands
    register_commands(app)
    return app
