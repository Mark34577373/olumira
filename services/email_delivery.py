"""Encrypted transactional outbox; SMTP happens only in the explicit worker."""
import json
import smtplib
import ssl
import time
import uuid
from urllib.parse import urlsplit
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from flask import current_app, render_template
from cryptography.fernet import Fernet
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import EmailOutbox, AccountToken
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


def deliver_pending(limit=20):
    if current_app.config['MAIL_BACKEND'] != 'smtp':
        raise ValueError('SMTP is not configured; use the private local preview command')
    sent, failed, cancelled = 0, 0, 0
    for _ in range(limit):
        with transaction() as store:
            moment = int(time.time())
            job = store.scalar(select(EmailOutbox).where(
                EmailOutbox.delivered_at.is_(None), EmailOutbox.cancelled_at.is_(None),
                EmailOutbox.available_at <= moment, EmailOutbox.attempts < 5
            ).order_by(EmailOutbox.created_at, EmailOutbox.id).with_for_update(skip_locked=True))
            if job is None:
                break
            token = store.get(AccountToken, job.token_hash) if job.token_hash else None
            if job.expires_at <= moment or (job.token_hash and (not token or token.used_at is not None or token.expires_at <= moment)):
                job.cancelled_at = moment
                cancelled += 1
                continue
            job.attempts += 1
            try:
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
