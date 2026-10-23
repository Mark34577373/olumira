"""HTTPS registration contract and security failures, with isolated accounts."""
import re,time
from unittest.mock import patch
import pytest
from sqlalchemy import select,func
from test_proxy_redirects import app, get, ORIGIN, FORWARDED
from support import PASSWORD
from olumira.extensions import db
from olumira.models import User
from test_account_recovery import email_link
from services.account_recovery import verify_email


def values(client):
    response=get(client,'/auth/register')
    assert response.headers['Referrer-Policy']=='same-origin'
    return dict(display_name='Fictional HTTPS signup',email='new-fictional@example.com',password=PASSWORD,
                confirm_password=PASSWORD,csrf_token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',response.text)[1])


def submit(client,data,**kwargs):
    return client.post('/auth/register',base_url=ORIGIN,
                       headers={**FORWARDED,'Referer':'https://olumira.onrender.com/auth/register'},data=data,**kwargs)


def count(app):
    with app.app_context():return db.session.scalar(select(func.count()).select_from(User))


def test_signup_duplicate_verification_login(app):
    client=app.test_client();data=values(client);before=count(app)
    response=submit(client,data);assert response.status_code==302 and response.location=='/auth/check-email'
    assert count(app)==before+1
    assert submit(client,values(client)).status_code==302 and count(app)==before+1
    code,_,_=email_link(app,'verify_email')
    with app.app_context():assert verify_email(code)
    page=get(client,'/auth/login');token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',page.text)[1]
    response=client.post('/auth/login',base_url=ORIGIN,headers={**FORWARDED,'Referer':'https://olumira.onrender.com/auth/login'},data=dict(email=data['email'],password=PASSWORD,csrf_token=token),follow_redirects=True)
    assert response.status_code==200 and response.request.path=='/setup'


@pytest.mark.parametrize('change',[{'display_name':''},{'email':'invalid'},{'password':'short','confirm_password':'short'},{'confirm_password':'different'}])
def test_invalid_fields_are_readable_without_creation(app,change):
    client=app.test_client();data=values(client);data.update(change);before=count(app)
    response=submit(client,data);assert response.status_code==422
    assert 'Please check the highlighted fields' in response.text and 'aria-invalid="true"' in response.text
    assert count(app)==before


@pytest.mark.parametrize('failure',['missing','invalid','session','expired','changed_key','referrer','cross_origin'])
def test_csrf_failures_remain_rejected(app,failure,caplog):
    client=app.test_client();data=values(client);before=count(app)
    if failure=='missing':data.pop('csrf_token')
    if failure=='invalid':data['csrf_token']='invalid-fictional-token'
    if failure=='session':client.delete_cookie('__Host-olumira_session',domain='olumira.onrender.com')
    if failure=='changed_key':app.secret_key='different-fictional-worker-secret'
    if failure in {'referrer','cross_origin'}:
        headers=dict(FORWARDED)
        if failure=='cross_origin':headers['Referer']='https://attacker.invalid/'
        response=client.post('/auth/register',base_url=ORIGIN,headers=headers,data=data)
    elif failure=='expired':
        future=time.time()+3601
        with patch('time.time',return_value=future):response=submit(client,data)
    else:response=submit(client,data)
    assert response.status_code==400 and 'Your form needs a refresh' in response.text
    assert count(app)==before and 'CSRF rejected:' in caplog.text
    assert data.get('csrf_token','not-in-log') not in caplog.text
    assert PASSWORD not in caplog.text and data['email'] not in caplog.text


def test_closed_registration_cannot_be_bypassed_with_invitation(app):
    app.config['REGISTRATION_ENABLED']=False
    client=app.test_client();page=get(client,'/auth/register')
    assert page.status_code==403 and 'Registration is currently closed' in page.text
    assert 'does not create an account' in page.text
    page=get(client,'/auth/login');token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',page.text)[1]
    data=dict(display_name='Fictional',email='closed@example.com',password=PASSWORD,confirm_password=PASSWORD,csrf_token=token,recovery_code='invalid-beta-code')
    before=count(app);response=submit(client,data)
    assert response.status_code==403 and count(app)==before
