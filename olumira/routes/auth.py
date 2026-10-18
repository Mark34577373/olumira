import hashlib
import hmac
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from email_validator import EmailNotValidError
from olumira.extensions import limiter
from olumira.forms import LoginForm, RegistrationForm
from services.authentication import normalize_email, register_user, authenticate, start_session, end_session

from olumira.privacy_logging import security_event

bp = Blueprint('auth', __name__, url_prefix='/auth')
SAFE_DESTINATIONS = frozenset({'/', '/routines', '/communication', '/observations', '/resources', '/auth/settings'})


def safe_destination(value):
    return value if value in SAFE_DESTINATIONS else url_for('dashboard.dashboard')


def account_rate_key():
    try:
        email = normalize_email(request.form.get('email', '')[:254])
    except EmailNotValidError:
        email = 'invalid'
    return hmac.new(current_app.secret_key.encode(), email.encode(), hashlib.sha256).hexdigest()


def settings_account_key():
    identity = current_user.get_id() if current_user.is_authenticated else 'anonymous'
    return hmac.new(current_app.secret_key.encode(), identity.encode(), hashlib.sha256).hexdigest()


@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_REGISTER_LIMIT'], methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = register_user(form.email.data, form.display_name.data, form.password.data)
        if user is not None:
            # Registration never implicitly grants a login session.
            from services.account_recovery import request_link
            request_link(user.email, 'verify_email')
        # Public response does not disclose whether the address already exists.
        return redirect(url_for('auth.check_email'))
    return render_template('auth/register.html', form=form), 422 if request.method == 'POST' else 200


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_LOGIN_IP_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['AUTH_LOGIN_ACCOUNT_LIMIT'], key_func=account_rate_key, methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    form, error = LoginForm(), None
    destination = safe_destination(request.form.get('next') or request.args.get('next'))
    if form.validate_on_submit():
        user = authenticate(form.email.data, form.password.data)
        if user and start_session(user):
            security_event('auth.login_success', user.id)
            return redirect(destination if user.email_verified else url_for('auth.verification'))
        error = 'Email or password is incorrect.'
    elif request.method == 'POST':
        error = 'Email or password is incorrect.'
    if error:
        security_event('auth.login_failed')
    return render_template('auth/login.html', form=form, error=error, destination=destination), 401 if error else 200


@bp.post('/logout')
@login_required
def logout():
    actor_id = current_user.id
    end_session()
    security_event('auth.logout', actor_id)
    flash('You’ve signed out safely.', 'success')
    return redirect(url_for('auth.login'))


GENERIC_LINK_MESSAGE = 'If an account needs this email, a link will arrive shortly. Check your inbox and spam folder.'


def _request_link_safely(email, purpose):
    from services.account_recovery import request_link
    from olumira.extensions import db
    try:
        request_link(email, purpose)
    except Exception:
        db.session.rollback()
        current_app.logger.warning('Account email request could not be queued; details redacted')


@bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_RECOVERY_IP_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['AUTH_RECOVERY_ACCOUNT_LIMIT'], key_func=account_rate_key, methods=['POST'])
def forgot_password():
    from olumira.forms import EmailRequestForm
    form = EmailRequestForm()
    if form.validate_on_submit():
        _request_link_safely(form.email.data, 'reset_password')
        return render_template('auth/message.html', heading='Check your email', message=GENERIC_LINK_MESSAGE)
    return render_template('auth/request_link.html', form=form, purpose='reset'), 422 if request.method == 'POST' else 200


@bp.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_RECOVERY_IP_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['AUTH_RECOVERY_ACCOUNT_LIMIT'], key_func=account_rate_key, methods=['POST'])
def resend_verification():
    from olumira.forms import EmailRequestForm
    form = EmailRequestForm()
    if form.validate_on_submit():
        _request_link_safely(form.email.data, 'verify_email')
        return render_template('auth/message.html', heading='Check your email', message=GENERIC_LINK_MESSAGE)
    return render_template('auth/request_link.html', form=form, purpose='verify'), 422 if request.method == 'POST' else 200


@bp.get('/check-email')
def check_email():
    return render_template('auth/message.html', heading='Check your email',
                           message='If this address can be registered, a verification link will arrive shortly. Existing members can sign in or request a password reset.')


@bp.get('/verification')
@login_required
def verification():
    if current_user.email_verified:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('auth/verification.html')


@bp.route('/verify-email', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_TOKEN_LIMIT'], methods=['POST'])
def verify_email():
    from olumira.forms import LinkForm
    from services.account_recovery import verify_email as consume
    form = LinkForm()
    error = None
    if form.validate_on_submit():
        result = consume(form.recovery_code.data)
        if result:
            if current_user.is_authenticated and current_user.id == result:
                end_session()
            security_event('auth.email_verified', result)
            return render_template('auth/message.html', heading='Email verified',
                                   message='Your email is confirmed. Sign in to start your day.')
        form.recovery_code.data = ''
        error = 'This verification link is invalid, expired, or already used. Request a new one to continue.'
    return render_template('auth/use_link.html', form=form, kind='verify', error=error), 410 if error else (422 if request.method == 'POST' else 200)


@bp.route('/reset-password', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_TOKEN_LIMIT'], methods=['POST'])
def reset_password():
    from olumira.forms import ResetPasswordForm
    from services.account_recovery import reset_password as consume
    form = ResetPasswordForm()
    error = None
    if form.validate_on_submit():
        result = consume(form.recovery_code.data, form.password.data)
        if result:
            if current_user.is_authenticated and current_user.id == result:
                end_session()
            security_event('auth.password_reset', result)
            return render_template('auth/message.html', heading='Password reset',
                                   message='Your password has been updated and previous sessions have ended. Sign in with your new password.')
        form.recovery_code.data = ''
        error = 'This reset link is invalid, expired, or already used. Request a new one to continue.'
    return render_template('auth/use_link.html', form=form, kind='reset', error=error), 410 if error else (422 if request.method == 'POST' else 200)


@bp.route('/confirm-email', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config['AUTH_TOKEN_LIMIT'], methods=['POST'])
def confirm_email():
    from olumira.forms import LinkForm
    from services.account_recovery import confirm_email_change
    form = LinkForm()
    error = None
    if form.validate_on_submit():
        result = confirm_email_change(form.recovery_code.data)
        if result:
            if current_user.is_authenticated and current_user.id == result:
                end_session()
            security_event('auth.email_changed', result)
            return render_template('auth/message.html', heading='Email updated',
                                   message='Your new email is verified and previous sessions have ended. Sign in with your new address.')
        form.recovery_code.data = ''
        error = 'This email-change link is invalid, expired, already used, or the address is unavailable.'
    return render_template('auth/use_link.html', form=form, kind='change', error=error), 410 if error else (422 if request.method == 'POST' else 200)


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@limiter.limit(lambda: current_app.config['AUTH_SETTINGS_LIMIT'], methods=['POST'])
@limiter.limit(lambda: current_app.config['AUTH_SETTINGS_LIMIT'], key_func=settings_account_key, methods=['POST'])
def settings():
    from olumira.forms import ProfileForm, ChangePasswordForm, ChangeEmailForm, ConfirmPasswordForm
    from services import account_recovery as accounts
    profile = ProfileForm(prefix='profile')
    email = ChangeEmailForm(prefix='email')
    password = ChangePasswordForm(prefix='password')
    cancel = ConfirmPasswordForm(prefix='cancel')
    sessions = ConfirmPasswordForm(prefix='sessions')
    status, error = 200, None
    if request.method == 'GET':
        profile.display_name.data = current_user.display_name
    else:
        action = request.form.get('action')
        if action != 'profile':
            profile.display_name.data = current_user.display_name
        forms = {'profile': profile, 'email': email, 'password': password, 'cancel': cancel, 'sessions': sessions}
        selected = forms.get(action)
        if not selected:
            from flask import abort
            abort(400)
        if selected.validate_on_submit():
            user_id = current_user.id
            if action == 'profile' and accounts.update_profile(user_id, profile.display_name.data):
                security_event('auth.profile_updated', user_id)
                flash('Your display name is updated.', 'success')
                return redirect(url_for('auth.settings'))
            if action == 'email' and accounts.request_email_change(user_id, email.current_password.data, email.email.data):
                security_event('auth.email_change_requested', user_id)
                flash('Check the new address for a confirmation link. Your current email stays active until you confirm.', 'success')
                return redirect(url_for('auth.settings'))
            if action == 'cancel' and accounts.cancel_email_change(user_id, cancel.current_password.data):
                security_event('auth.email_change_cancelled', user_id)
                flash('The pending email change is cancelled.', 'success')
                return redirect(url_for('auth.settings'))
            if action == 'password' and accounts.change_password(user_id, password.current_password.data, password.password.data):
                security_event('auth.password_changed', user_id)
                end_session()
                flash('Your password is updated. All sessions have ended. Sign in again.', 'success')
                return redirect(url_for('auth.login'))
            if action == 'sessions' and accounts.sign_out_everywhere(user_id, sessions.current_password.data):
                security_event('auth.sessions_revoked', user_id)
                end_session()
                flash('All sessions have ended. Sign in to continue.', 'success')
                return redirect(url_for('auth.login'))
            error = 'We couldn’t make that change. Check your current password and the details you entered.'
        else:
            error = 'Please check the highlighted fields.'
        status = 422
    return render_template('auth/settings.html', profile=profile, email=email, password=password,
                           cancel=cancel, sessions=sessions, error=error), status
