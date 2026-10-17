"""Fictional account helpers; all requests retain real CSRF enforcement."""
import re
from services.authentication import register_user

PASSWORD = 'Fictional cedar trail passphrase 42'


def csrf_token(client):
    html = client.get('/auth/settings', follow_redirects=True).text
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


def create_historical_user(app, email):
    """Seed a real pre-0021 schema without asking today's ORM for future columns.

    Migration fixtures use explicit historical SQL so additive account columns do
    not require the old schema to already contain their future definitions.
    """
    import uuid
    from sqlalchemy import text
    from werkzeug.security import generate_password_hash
    from services.authentication import PASSWORD_METHOD
    from services.database import STARTER_ROUTINES
    from olumira.extensions import db
    uid, wid = uuid.uuid4().hex, uuid.uuid4().hex
    with app.app_context():
        with db.engine.begin() as c:
            values=dict(uid=uid,wid=wid,email=email,password=generate_password_hash(PASSWORD,method=PASSWORD_METHOD))
            c.execute(text("INSERT INTO owners(id,created_at) VALUES (:wid,'2026-10-17')"),values)
            c.execute(text("INSERT INTO users(id,email,password_hash,display_name,email_verified,created_at,updated_at,owner_id,auth_version) VALUES (:uid,:email,:password,'Fictional caregiver',true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,:wid,0)"),values)
            c.execute(text("INSERT INTO family_workspaces(id,name,created_by,created_at,updated_at) VALUES (:wid,'Our Family',:uid,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),values)
            c.execute(text("INSERT INTO workspace_memberships(id,workspace_id,user_id,role,status,joined_at) VALUES (:wid,:wid,:uid,'owner','active',CURRENT_TIMESTAMP)"),values)
            for name,category in STARTER_ROUTINES:
                rid=c.execute(text("INSERT INTO routines(owner_id,workspace_id,name,category) VALUES (:wid,:wid,:name,:category) RETURNING id"),dict(wid=wid,name=name,category=category)).scalar_one()
                c.execute(text("INSERT INTO routine_steps(id,routine_id,title,description,icon,position,created_at,updated_at) VALUES (:id,:rid,:name,'','sun',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),dict(id=uuid.uuid4().hex,rid=rid,name=name))
    return uid,wid
