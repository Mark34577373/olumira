"""Environment configuration. Production never falls back to a local database."""
import os
import base64
import hashlib
import secrets
from urllib.parse import urlsplit
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_SECRET = 'dev-only-secret-change-me'


def configuration(overrides=None):
    overrides = overrides or {}
    environment = overrides.get('APP_ENV', os.getenv('APP_ENV', 'production' if os.getenv('RENDER') else 'development'))
    if environment not in {'development', 'testing', 'production'}:
        raise ValueError('APP_ENV must be development, testing, or production')
    secret = os.getenv('SECRET_KEY')
    database_url = os.getenv('DATABASE_URL') if environment != 'testing' else None
    values = dict(
        APP_ENV=environment, SECRET_KEY=(secrets.token_urlsafe(48) if environment == 'testing' else secret or DEV_SECRET),
        DATABASE=':memory:' if environment == 'testing' else str(ROOT / 'database' / 'olumira.db'),
        DATABASE_URL=database_url,
        TESTING=environment == 'testing', DEBUG=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=environment == 'production',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_COOKIE_NAME='__Host-olumira_session' if environment == 'production' else 'olumira_session',
        SESSION_COOKIE_PATH='/', SESSION_COOKIE_DOMAIN=None,
        AUTH_SESSION_SECONDS=int(os.getenv('AUTH_SESSION_SECONDS', '43200')),
        AUTH_IDLE_SECONDS=int(os.getenv('AUTH_IDLE_SECONDS', '1800')),
        AUTH_LOGIN_IP_LIMIT='10 per minute; 100 per hour',
        AUTH_LOGIN_ACCOUNT_LIMIT='20 per hour',
        AUTH_REGISTER_LIMIT='5 per hour',
        REGISTRATION_ENABLED=os.getenv('REGISTRATION_ENABLED', 'true').lower() == 'true',
        AUTH_RECOVERY_IP_LIMIT='5 per hour', AUTH_RECOVERY_ACCOUNT_LIMIT='3 per hour',
        AUTH_SETTINGS_LIMIT='10 per hour', AUTH_TOKEN_LIMIT='10 per hour',
        INVITATION_SECONDS=int(os.getenv('INVITATION_SECONDS', '86400')),
        WORKSPACE_INVITE_LIMIT='10 per hour',
        WORKSPACE_CREATE_LIMIT='10 per hour',
        VERIFY_TOKEN_SECONDS=int(os.getenv('VERIFY_TOKEN_SECONDS', '3600')),
        RESET_TOKEN_SECONDS=int(os.getenv('RESET_TOKEN_SECONDS', '1800')),
        EMAIL_CHANGE_TOKEN_SECONDS=int(os.getenv('EMAIL_CHANGE_TOKEN_SECONDS', '1800')),
        PUBLIC_APP_URL='http://127.0.0.1:5000' if environment == 'testing' else os.getenv('PUBLIC_APP_URL', 'http://127.0.0.1:5000' if environment != 'production' else ''),
        MAIL_BACKEND=os.getenv('MAIL_BACKEND', 'development' if environment != 'production' else 'smtp'),
        MAIL_FROM=os.getenv('MAIL_FROM', 'Olumira <no-reply@example.com>'),
        MAIL_ENCRYPTION_KEY=None if environment == 'testing' else os.getenv('MAIL_ENCRYPTION_KEY'),
        SMTP_HOST=os.getenv('SMTP_HOST', ''), SMTP_PORT=int(os.getenv('SMTP_PORT', '587')),
        SMTP_USERNAME=os.getenv('SMTP_USERNAME', ''), SMTP_PASSWORD=os.getenv('SMTP_PASSWORD', ''),
        SMTP_SECURITY=os.getenv('SMTP_SECURITY', 'starttls'), SMTP_TIMEOUT=10,
        RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
        RATELIMIT_HEADERS_ENABLED=True,
        RATELIMIT_SWALLOW_ERRORS=False,
        RATELIMIT_IN_MEMORY_FALLBACK_ENABLED=False,
        TRUSTED_PROXY_HOPS=int(os.getenv('TRUSTED_PROXY_HOPS', '0')),
        TRUSTED_HOSTS=[host.strip() for host in os.getenv('TRUSTED_HOSTS', '').split(',') if host.strip()] or None,
        MAX_CONTENT_LENGTH=64 * 1024,
        WTF_CSRF_TIME_LIMIT=3600,
        APP_TIMEZONE=os.getenv('APP_TIMEZONE', 'America/Chicago'),
    )
    values.update(overrides)
    if environment == 'production':
        if not values['SECRET_KEY'] or values['SECRET_KEY'] == DEV_SECRET:
            raise ValueError('Production requires SECRET_KEY')
        if not values['DATABASE_URL'] or not values['DATABASE_URL'].startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
            raise ValueError('Production requires a PostgreSQL DATABASE_URL')
        if not values['RATELIMIT_STORAGE_URI'].startswith(('redis://', 'rediss://')):
            raise ValueError('Production requires shared Redis rate-limit storage')
        if len(values['SECRET_KEY']) < 32:
            raise ValueError('Production SECRET_KEY must have at least 32 characters')
        values['WTF_CSRF_ENABLED'] = True
        values['RATELIMIT_ENABLED'] = True
        values['DEBUG'] = False
        values['TESTING'] = False
        values['SESSION_COOKIE_SECURE'] = True
        values['SESSION_COOKIE_HTTPONLY'] = True
        values['SESSION_COOKIE_SAMESITE'] = 'Lax'
        values['SESSION_COOKIE_NAME'] = '__Host-olumira_session'
        values['SESSION_COOKIE_PATH'] = '/'
        values['SESSION_COOKIE_DOMAIN'] = None
    if not 0 <= values['TRUSTED_PROXY_HOPS'] <= 2:
        raise ValueError('TRUSTED_PROXY_HOPS must be 0, 1, or 2')
    if not 60 <= values['AUTH_IDLE_SECONDS'] <= values['AUTH_SESSION_SECONDS'] <= 604800:
        raise ValueError('Session timeouts must be between one minute and seven days, idle <= absolute')
    public_url = urlsplit(values['PUBLIC_APP_URL'])
    if public_url.scheme not in {'http', 'https'} or not public_url.hostname or public_url.username or public_url.password or public_url.query or public_url.fragment or public_url.path not in {'', '/'}:
        raise ValueError('PUBLIC_APP_URL must be a canonical application origin')
    if values['MAIL_BACKEND'] not in {'development', 'smtp'} or values['SMTP_SECURITY'] not in {'starttls', 'ssl'}:
        raise ValueError('Use development or TLS-protected SMTP email delivery')
    for setting in ('VERIFY_TOKEN_SECONDS', 'RESET_TOKEN_SECONDS', 'EMAIL_CHANGE_TOKEN_SECONDS', 'INVITATION_SECONDS'):
        if not 60 <= values[setting] <= 86400:
            raise ValueError('Account token lifetimes must be between one minute and one day')
    if environment == 'production':
        if public_url.scheme != 'https' or not values['MAIL_ENCRYPTION_KEY']:
            raise ValueError('Production requires HTTPS PUBLIC_APP_URL and MAIL_ENCRYPTION_KEY')
        if values['MAIL_BACKEND'] != 'smtp' or not all(values[key] for key in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD')) or values['MAIL_FROM'] == 'Olumira <no-reply@example.com>':
            raise ValueError('Production requires authenticated SMTP and a configured sender')
    if environment == 'testing':
        # Test processes cannot accidentally deliver real email.
        values['MAIL_BACKEND'] = 'development'
        values['RATELIMIT_STORAGE_URI'] = 'memory://'
        values['MAIL_ENCRYPTION_KEY'] = overrides.get('MAIL_ENCRYPTION_KEY')
        values['PUBLIC_APP_URL'] = overrides.get('PUBLIC_APP_URL', 'http://127.0.0.1:5000')
    if not values['MAIL_ENCRYPTION_KEY']:
        values['MAIL_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(hashlib.sha256(('development-mail:' + values['SECRET_KEY']).encode()).digest()).decode()
    from cryptography.fernet import Fernet
    try:
        Fernet(values['MAIL_ENCRYPTION_KEY'].encode())
    except (ValueError, TypeError):
        raise ValueError('MAIL_ENCRYPTION_KEY must be a valid Fernet key') from None
    values['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=values['AUTH_SESSION_SECONDS'])
    url = values.get('DATABASE_URL') or 'sqlite:///' + values['DATABASE']
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if environment == 'testing':
        from sqlalchemy.engine import make_url
        parsed = make_url(url)
        if parsed.get_backend_name() == 'sqlite' and parsed.database not in (None, '', ':memory:'):
            target = Path(parsed.database).resolve()
            normal = (ROOT / 'database' / 'olumira.db').resolve()
            if target == normal or target.is_file() and normal.is_file() and target.samefile(normal):
                raise ValueError('Testing must not use the normal application database')
    if environment == 'production' and not values['TRUSTED_HOSTS']:
        values['TRUSTED_HOSTS'] = [public_url.hostname]
    values['SQLALCHEMY_DATABASE_URI'] = url
    values['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    values['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'hide_parameters': True}
    if environment == 'production':
        from sqlalchemy.engine import make_url
        parsed = make_url(url)
        if parsed.query.get('sslmode') != 'verify-full':
            raise ValueError('Production PostgreSQL requires sslmode=verify-full and a trusted certificate chain')
        options = values['SQLALCHEMY_ENGINE_OPTIONS']
        options.update(pool_size=3, max_overflow=1, pool_timeout=3, pool_recycle=300,
                       connect_args={'connect_timeout': 3, 'options': '-c statement_timeout=10000 -c lock_timeout=3000'})
        values['RATELIMIT_STORAGE_OPTIONS'] = {'socket_connect_timeout': 2, 'socket_timeout': 2}
    return values
