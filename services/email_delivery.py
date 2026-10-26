"""Encrypted transactional outbox; SMTP worker and opt-in HTTPS request delivery."""
import json
import smtplib
import ssl
import time
import uuid
import http.client
from urllib.parse import urlsplit
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from flask import current_app, render_template, g, has_request_context
from cryptography.fernet import Fernet
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import EmailOutbox, AccountToken, WorkspaceInvitation
from services.database import transaction

SUBJECTS = {'verify_email': 'Verify your Olumira email', 'reset_password': 'Reset your Olumira password',
            'change_email': 'Confirm your new Olumira email', 'password_changed': 'Your Olumira password changed',
            'email_changed': 'Your Olumira email changed'}


def cipher():
    return Fernet(current_app.config['MAIL_ENCRYPTION_KEY'].encode())


def queue_email(user, kind, recipient, *, token=None, expires_at=None, new_email=None):
    moment = int(time.time())
    link = current_app.config['PUBLIC_APP_URL'].rstrip('/')
    raw, digest = token if token else (None, None)
    endpoint = {'verify_email': 'auth.verify_email', 'change_email': 'auth.confirm_email',
                'reset_password': 'auth.reset_password'}.get(kind, 'auth.forgot_password')
    link += current_app.url_map.bind(urlsplit(link).netloc).build(endpoint)
    if raw:
        # Fragments do not travel in HTTP request URLs, proxy/access logs, or referrers.
        link += '#token=' + raw
    values = dict(link=link, code=raw, minutes=max(1, ((expires_at or moment + 3600) - moment) // 60), new_email=new_email)
    payload = dict(recipient=recipient, subject=SUBJECTS[kind],
                   text=render_template('emails/' + kind + '.txt', **values),
                   html=render_template('emails/' + kind + '.html', **values))
    job = EmailOutbox(id=uuid.uuid4().hex, user_id=user.id, token_hash=digest, kind=kind,
                      encrypted_payload=cipher().encrypt(json.dumps(payload).encode()).decode(),
                      created_at=moment, available_at=moment, expires_at=expires_at or moment + 86400, attempts=0)
    db.session.add(job)
    if has_request_context():
        g.queued_email_ids = getattr(g, 'queued_email_ids', []) + [job.id]
    return job


def message_for(job):
    payload = json.loads(cipher().decrypt(job.encrypted_payload.encode()))
    message = EmailMessage(policy=SMTP)
    message['From'] = current_app.config['MAIL_FROM']
    message['To'] = payload['recipient']
    message['Subject'] = payload['subject']
    message['Date'] = formatdate(job.created_at, usegmt=True)
    message['Message-ID'] = f'<olumira-{job.id}@{current_app.config["PUBLIC_APP_URL"].split("//", 1)[1].split(":", 1)[0].rstrip("/")}>'
    message.set_content(payload['text'])
    message.add_alternative(payload['html'], subtype='html')
    return message


def send_smtp(message):
    settings = current_app.config
    context = ssl.create_default_context()
    if settings['SMTP_SECURITY'] == 'ssl':
        connection = smtplib.SMTP_SSL(settings['SMTP_HOST'], settings['SMTP_PORT'], timeout=settings['SMTP_TIMEOUT'], context=context)
    else:
        connection = smtplib.SMTP(settings['SMTP_HOST'], settings['SMTP_PORT'], timeout=settings['SMTP_TIMEOUT'])
    with connection as transport:
        if settings['SMTP_SECURITY'] == 'starttls':
            transport.ehlo()
            transport.starttls(context=context)
            transport.ehlo()
        transport.login(settings['SMTP_USERNAME'], settings['SMTP_PASSWORD'])
        refused = transport.send_message(message)
        if refused:
            raise smtplib.SMTPException('Recipient refused')


def send_resend(message, job_id):
    """Fixed HTTPS endpoint, verified system trust, no redirects or response-body logging."""
    payload = dict(from_=str(message['From']), to=[str(message['To'])],
                   subject=str(message['Subject']),
                   text=message.get_body(preferencelist=('plain',)).get_content(),
                   html=message.get_body(preferencelist=('html',)).get_content(),
                   headers={'Message-ID': str(message['Message-ID'])})
    payload['from'] = payload.pop('from_')
    connection = http.client.HTTPSConnection('api.resend.com', timeout=5,
                                              context=ssl.create_default_context())
    try:
        connection.request('POST', '/emails', body=json.dumps(payload).encode(), headers={
            'Authorization': 'Bearer ' + current_app.config['RESEND_API_KEY'],
            'Content-Type': 'application/json', 'User-Agent': 'Olumira/1.0',
            'Idempotency-Key': 'olumira-' + job_id})
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise RuntimeError('Email provider rejected request')
        result = json.loads(response.read(8192))
        if not isinstance(result, dict) or not result.get('id'):
            raise RuntimeError('Email provider did not acknowledge request')
    finally:
        connection.close()


def dispatch_request_email(response):
    """Send only this request's committed jobs; never scan other users' mail."""
    ids = getattr(g, 'queued_email_ids', [])
    if (response.status_code >= 400 or not ids or
            current_app.config['MAIL_BACKEND'] != 'resend' or
            current_app.config['MAIL_DELIVERY_MODE'] != 'request'):
        return response
    # Never flush or commit unfinished application writes from a response hook.
    if db.session.new or db.session.dirty or db.session.deleted:
        return response
    try:
        deliver_pending(limit=min(len(ids), 3), job_ids=ids)
    except Exception:
        db.session.rollback()
        current_app.logger.warning('Transactional email dispatch unavailable; details redacted')
    return response


def deliver_pending(limit=20, *, job_ids=None):
    if current_app.config['MAIL_BACKEND'] not in {'smtp', 'resend'}:
        raise ValueError('Email transport is not configured; use the private local preview command')
    sent, failed, cancelled = 0, 0, 0
    for _ in range(limit):
        with transaction() as store:
            moment = int(time.time())
            query = select(EmailOutbox).where(
                EmailOutbox.delivered_at.is_(None), EmailOutbox.cancelled_at.is_(None),
                EmailOutbox.available_at <= moment, EmailOutbox.attempts < 5
            ).order_by(EmailOutbox.created_at, EmailOutbox.id).with_for_update(skip_locked=True)
            if job_ids is not None:
                query = query.where(EmailOutbox.id.in_(job_ids))
            job = store.scalar(query)
            if job is None:
                break
            token = store.get(AccountToken, job.token_hash) if job.token_hash else None
            invitation = store.get(WorkspaceInvitation, job.invitation_id) if job.invitation_id else None
            invalid_invitation = job.invitation_id and (not invitation or invitation.revoked_at is not None or invitation.accepted_at is not None or invitation.expires_at <= moment)
            if invalid_invitation or job.expires_at <= moment or (job.token_hash and (not token or token.used_at is not None or token.expires_at <= moment)):
                job.cancelled_at = moment
                cancelled += 1
                continue
            job.attempts += 1
            try:
                if current_app.config['MAIL_BACKEND'] == 'resend':
                    send_resend(message_for(job), job.id)
                else:
                    send_smtp(message_for(job))
            except Exception:
                # Transport errors can embed recipients, credentials, and full messages.
                job.last_error = 'delivery_failed'
                job.available_at = moment + 60 * 2 ** (job.attempts - 1)
                current_app.logger.warning('Transactional email delivery failed; details redacted')
                failed += 1
            else:
                job.delivered_at, job.last_error = moment, None
                sent += 1
    return dict(sent=sent, failed=failed, cancelled=cancelled)


def expired_payloads(*, apply=False, now=None):
    """Explicit retention: scrub expired message bodies, retain delivery metadata.

    Dry-run by default. Account/invitation workers already refuse expired jobs.
    Does not affect usable links, private care records, or infrastructure backups.
    """
    from sqlalchemy import func, update
    moment = int(time.time()) if now is None else int(now)
    criteria = (EmailOutbox.expires_at <= moment, EmailOutbox.encrypted_payload != '')
    if not apply:
        return db.session.scalar(select(func.count()).select_from(EmailOutbox).where(*criteria))
    with transaction():
        return db.session.execute(update(EmailOutbox).where(*criteria).values(encrypted_payload='')).rowcount
