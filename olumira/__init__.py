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
    from .privacy_logging import configure_access_logging
    configure_access_logging()

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
    @app.before_request
    def routine_builder_body_limit():
        # Maximum valid 30-step UTF-8 forms can exceed the default 64 KiB after
        # URL encoding. Increase only these bounded builder POSTs, before CSRF
        # parses the body; account and other forms retain the stricter limit.
        if request.method == 'POST' and request.endpoint in {'routines.new_routine', 'routines.edit_builder', 'communication.board_editor'}:
            request.max_content_length = 256 * 1024

    @app.before_request
    def production_transport():
        if app.config['APP_ENV'] == 'production' and not request.is_secure and request.endpoint not in {'health.live', 'health.ready'}:
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                from flask import abort
                abort(400, description='HTTPS is required')
            return redirect(app.config['PUBLIC_APP_URL'].rstrip('/') + request.full_path.rstrip('?'), code=308)

    csrf.init_app(app)

    from .routes import dashboard, routines, communication, observations, resources, auth, workspaces, care, calendar, onboarding, settings, notifications, privacy, public
    for module in (dashboard, routines, communication, observations, resources, auth, workspaces, care, calendar, onboarding, settings, notifications, privacy, public):
        app.register_blueprint(module.bp)

    protected_blueprints = {'dashboard', 'routines', 'communication', 'observations', 'resources', 'workspaces', 'care', 'calendar', 'onboarding', 'settings', 'notifications', 'privacy'}

    @login_manager.unauthorized_handler
    def require_login():
        expired = getattr(g, 'auth_expired', False)
        session.clear()
        flash('Your session ended. Please sign in again.' if expired else 'Sign in to continue.', 'info')
        # Only the fixed application path is retained, never arbitrary query strings.
        return redirect(url_for('auth.login', next=request.path))

    @app.before_request
    def authorize_workspace():
        # Account security remains available without membership. Verified users
        # still receive the same authorized navigation context as product pages.
        if request.endpoint == 'dashboard.dashboard' and request.path == '/' and not current_user.is_authenticated and not getattr(g, 'auth_expired', False):
            return
        if request.endpoint == 'auth.settings' and current_user.is_authenticated and current_user.email_verified:
            from services.workspaces import resolve_context
            resolve_context()
            return
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
        if request.blueprint not in {'workspaces', 'privacy'} and not g.workspace_id:
            return redirect(url_for('workspaces.index'))
        if request.method == 'POST' and request.blueprint != 'workspaces':
            permission = {
                'care.task_editor': 'care.manage',
                'care.task_status': 'care.manage',
                'care.handoff_editor': 'care.manage',
                'care.acknowledge': 'care.acknowledge',
                'communication.communication_settings': 'communication.manage',
                'communication.favorite_action': 'communication.manage',
                'communication.board_editor': 'communication.manage',
                'communication.board_action': 'communication.manage',
                'communication.phrase_editor': 'communication.manage',
                'communication.phrase_action': 'communication.manage',
                'routines.routine_schedule': 'routines.edit',
                'routines.schedule_action': 'routines.edit',
                'routines.start_session': 'routines.complete',
                'routines.session_action': 'routines.complete',
                'routines.new_routine': 'routines.create',
                'routines.edit_builder': 'routines.edit',
                'routines.duplicate_routine': 'routines.create',
                'routines.restore_routine': 'routines.edit',
                'routines.archive_routine': 'routines.edit',
                'routines.add_routine_route': 'routines.create',
                'routines.add_template_route': 'routines.create',
                'routines.toggle_routine_completion': 'routines.complete',
                'routines.edit_routine_route': 'routines.edit',
                'routines.delete_routine_route': 'routines.edit',
                'observations.observations': 'observations.create',
                'observations.archive': 'observations.edit',
                'observations.reports': 'reports.generate',
                'observations.edit_observation_route': 'observations.edit',
            }.get(request.endpoint)
            if permission:
                require(permission, lock=True)

    @app.context_processor
    def workspace_template_helpers():
        from services.workspaces import can
        return {'can': can}

    @app.context_processor
    def personal_display():
        from flask import has_request_context
        if has_request_context() and current_user.is_authenticated:
            from services.personal_settings import get
            values = {'personal_pref': get(), 'notification_count': 0, 'notification_preview': []}
            if request.blueprint != 'public' and getattr(g, 'workspace_id', None) and current_user.email_verified:
                from services.notifications import unread_count, inbox
                values.update(notification_count=unread_count(), notification_preview=inbox(state='unread')[:3])
            return values
        return {'personal_pref': None}

    @app.after_request
    def security_headers(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'private, no-store, max-age=0' if request.endpoint in {'observations.reports','privacy.download'} else 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")
        if app.config['APP_ENV'] == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    messages = {
        400: ('Let’s check that request', 'Some information was missing or could not be accepted. Please go back and try again.'),
        403: ('This action needs permission', 'Your workspace role does not allow this action. Ask a workspace owner for help.'),
        404: ('This page has wandered off', 'We couldn’t find that page or item. You can return to your dashboard to continue.'),
        405: ('That action isn’t available here', 'Please use the page controls to complete this action.'),
        409: ('This item has changed', 'Another caregiver may have updated this item. Reload the latest version before trying again.'),
        413: ('This form is a little too large', 'Shorten the text or use fewer steps, then try again. Your saved routine has not changed.'),
        429: ('Let’s take a short pause', 'Too many attempts. Please wait a while before trying again.'),
        500: ('Something needs a little attention', 'We couldn’t complete your request. Please try again in a moment.'),
    }

    def error_page(error):
        from werkzeug.exceptions import SecurityError
        if isinstance(error, SecurityError):
            # Rejected Host values have no URL adapter; never render url_for.
            from flask import Response
            return Response('Invalid request host.', status=400, mimetype='text/plain')
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

    from .infrastructure import register as register_infrastructure
    register_infrastructure(app)

    from .commands import register_commands
    register_commands(app)
    from .mail_commands import register_mail_commands
    register_mail_commands(app)
    return app
