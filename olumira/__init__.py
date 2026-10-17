"""Application construction without schema changes or destructive startup tasks."""
from pathlib import Path
from flask import Flask, g, render_template, request, session, redirect, url_for, flash
from flask_login import current_user
from .config import configuration


class OlumiraFlask(Flask):
    def log_exception(self, exc_info):
        # Exception strings can contain SQL parameters or private submitted data.
        self.logger.error('Unhandled request failure: endpoint=%s', request.endpoint)



def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    app = OlumiraFlask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(configuration(config))

    from .extensions import db, migrate, login_manager, limiter, csrf
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

    from werkzeug.middleware.proxy_fix import ProxyFix
    hops = app.config['TRUSTED_PROXY_HOPS']
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=0)
    login_manager.init_app(app)
    login_manager.session_protection = 'strong'
    login_manager.login_view = 'auth.login'
    from services.authentication import load_user
    login_manager.user_loader(load_user)
    limiter.init_app(app)
    csrf.init_app(app)

    from .routes import dashboard, routines, communication, observations, resources, auth, workspaces
    for module in (dashboard, routines, communication, observations, resources, auth, workspaces):
        app.register_blueprint(module.bp)

    protected_blueprints = {'dashboard', 'routines', 'communication', 'observations', 'resources', 'workspaces'}

    @login_manager.unauthorized_handler
    def require_login():
        expired = getattr(g, 'auth_expired', False)
        session.clear()
        flash('Your session ended. Please sign in again.' if expired else 'Sign in to continue.', 'info')
        # Only the fixed application path is retained, never arbitrary query strings.
        return redirect(url_for('auth.login', next=request.path))

    @app.before_request
    def authorize_workspace():
        if request.endpoint == 'workspaces.accept':
            return
        if request.blueprint not in protected_blueprints:
            return
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        # Cookie-supplied legacy owner_id is never used for authorization.
        if not current_user.email_verified:
            return redirect(url_for('auth.verification'))
        from services.workspaces import resolve_context, require
        resolve_context()
        if request.blueprint != 'workspaces' and not g.workspace_id:
            return redirect(url_for('workspaces.index'))
        if request.method == 'POST' and request.blueprint != 'workspaces':
            permission = {
                'routines.add_routine_route': 'routines.create',
                'routines.add_template_route': 'routines.create',
                'routines.toggle_routine_completion': 'routines.complete',
                'routines.edit_routine_route': 'routines.edit',
                'routines.delete_routine_route': 'routines.edit',
                'observations.observations': 'observations.create',
                'observations.edit_observation_route': 'observations.edit',
            }.get(request.endpoint)
            if permission:
                require(permission, lock=True)

    @app.context_processor
    def workspace_template_helpers():
        from services.workspaces import can
        return {'can': can}

    @app.after_request
    def security_headers(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        if app.config['APP_ENV'] == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    messages = {
        400: ('Let’s check that request', 'Some information was missing or could not be accepted. Please go back and try again.'),
        403: ('This action needs permission', 'Your workspace role does not allow this action. Ask a workspace owner for help.'),
        404: ('This page has wandered off', 'We couldn’t find that page or item. You can return to your dashboard to continue.'),
        405: ('That action isn’t available here', 'Please use the page controls to complete this action.'),
        429: ('Let’s take a short pause', 'Too many attempts. Please wait a while before trying again.'),
        500: ('Something needs a little attention', 'We couldn’t complete your request. Please try again in a moment.'),
    }

    def error_page(error):
        code = getattr(error, 'code', 500)
        if code >= 500:
            # Log only the status and endpoint, never form data, SQL or exception strings.
            app.logger.error('Request failed: status=%s endpoint=%s', code, request.endpoint)
        if code == 403 and getattr(g, 'membership', None) is not None and current_user.is_authenticated:
            # Abort must never commit a partially executed care operation. Record
            # the denied capability only after rolling back that transaction.
            db.session.rollback()
            try:
                from services.workspaces import audit
                audit('permission.denied', g.workspace_id, current_user.id, request.endpoint)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.warning('Permission denial audit could not be recorded; details redacted')
        title, message = messages[code]
        response = error.get_response()
        response.data = render_template('error.html', code=code, heading=title, message=message)
        response.content_type = 'text/html; charset=utf-8'
        return response

    for code in messages:
        app.register_error_handler(code, error_page)
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('error.html', code=400, heading='Your form needs a refresh',
                               message='For your security, please refresh the page and try again.'), 400

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        return error_page(InternalServerError())

    from .commands import register_commands
    register_commands(app)
    from .mail_commands import register_mail_commands
    register_mail_commands(app)
    return app
