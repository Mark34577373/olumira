from pathlib import Path
import click
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import EmailOutbox
from services.email_delivery import message_for, deliver_pending


def register_mail_commands(app):
    @app.cli.command('mail-retention')
    @click.option('--apply', is_flag=True, help='Scrub expired encrypted payloads; default is a dry run.')
    def mail_retention(apply):
        """Retain delivery metadata while minimizing expired recipient/token/message content."""
        from services.email_delivery import expired_payloads
        try:
            count = expired_payloads(apply=apply)
        except Exception:
            db.session.rollback()
            raise click.ClickException('Mail retention failed; inspect privately. No payloads were logged.') from None
        click.echo(f'{"Scrubbed" if apply else "Would scrub"} {count} expired email payloads. Delivery metadata and backups are retained.')

    @app.cli.command('mail-send-pending')
    @click.option('--limit', default=20, type=click.IntRange(1, 100))
    def send_pending(limit):
        """Deliver queued messages through configured SMTP or HTTPS transport."""
        try:
            counts = deliver_pending(limit)
        except Exception:
            raise click.ClickException('Email worker could not complete. Check configuration locally; details redacted.') from None
        click.echo(f'Email worker counts: {counts}')
        if counts['failed']:
            raise click.ClickException('Some messages need retry. No recipients or message contents were logged.')

    @app.cli.command('mail-queue')
    def queue_status():
        """List message IDs and non-sensitive delivery state only."""
        jobs = db.session.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(50))
        for job in jobs:
            state = 'delivered' if job.delivered_at else 'cancelled' if job.cancelled_at else 'retry exhausted' if job.attempts >= 5 else 'pending'
            click.echo(f'{job.id} {job.kind} {state} attempts={job.attempts}')

    @app.cli.command('mail-preview')
    @click.option('--output', required=True, type=click.Path(dir_okay=False))
    @click.option('--message-id', default=None)
    def preview(output, message_id):
        """Save one private .eml in development; never print links or codes."""
        if app.config['APP_ENV'] == 'production' or app.config['MAIL_BACKEND'] != 'development':
            raise click.ClickException('Private previews are only available in local development/testing.')
        try:
            query = select(EmailOutbox).where(EmailOutbox.cancelled_at.is_(None))
            query = query.where(EmailOutbox.id == message_id) if message_id else query.order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc())
            job = db.session.scalar(query.limit(1))
            if job is None:
                raise ValueError('No queued message')
            message = message_for(job)
            destination = Path(output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation with private permissions avoids even a brief readable-file window.
            import os
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(message.as_bytes())
        except Exception:
            raise click.ClickException('Preview failed or the file already exists. No message contents were logged.') from None
        click.echo('Private email preview saved. Open the requested file locally; keep it out of Git.')
