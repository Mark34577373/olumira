"""Environment configuration. Production never falls back to a local database."""
import os
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
        APP_ENV=environment, SECRET_KEY=secret or DEV_SECRET,
        DATABASE=str(ROOT / 'database' / 'olumira.db'),
        DATABASE_URL=database_url,
        TESTING=environment == 'testing', DEBUG=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=environment == 'production',
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        APP_TIMEZONE=os.getenv('APP_TIMEZONE', 'America/Chicago'),
    )
    values.update(overrides)
    if environment == 'production':
        if not values['SECRET_KEY'] or values['SECRET_KEY'] == DEV_SECRET:
            raise ValueError('Production requires SECRET_KEY')
        if not values['DATABASE_URL'] or not values['DATABASE_URL'].startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
            raise ValueError('Production requires a PostgreSQL DATABASE_URL')
        values['DEBUG'] = False
        values['TESTING'] = False
        values['SESSION_COOKIE_SECURE'] = True
    url = values.get('DATABASE_URL') or 'sqlite:///' + values['DATABASE']
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    values['SQLALCHEMY_DATABASE_URI'] = url
    values['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    values['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'hide_parameters': True}
    return values
