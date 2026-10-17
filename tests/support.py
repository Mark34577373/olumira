"""Fictional account helpers; all requests retain real CSRF enforcement."""
import re
from services.authentication import register_user

PASSWORD = 'Fictional cedar trail passphrase 42'


def csrf_token(client):
    html = client.get('/', follow_redirects=True).text
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if match is None:
        raise AssertionError('Page did not provide a CSRF token')
    return match.group(1)


def post(client, path, data=None, **kwargs):
    values = dict(data or {})
    values.setdefault('csrf_token', csrf_token(client))
    return client.post(path, data=values, **kwargs)


def create_user(app, email='fictional@example.com'):
    with app.app_context():
        user = register_user(email, 'Fictional caregiver', PASSWORD)
        user.email_verified = True
        from olumira.extensions import db
        db.session.commit()
        return user.id, user.owner_id


def login(client, email='fictional@example.com'):
    response = post(client, '/auth/login', {'email': email, 'password': PASSWORD})
    assert response.status_code == 302, response.text
    return response


def production_mail_settings():
    from cryptography.fernet import Fernet
    return dict(PUBLIC_APP_URL='https://olumira.example.com', MAIL_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                MAIL_BACKEND='smtp', MAIL_FROM='Olumira <test-sender@example.com>', SMTP_HOST='smtp.example.com',
                SMTP_USERNAME='fictional-user', SMTP_PASSWORD='fictional-not-a-real-credential')
