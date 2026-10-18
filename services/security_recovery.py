"""Explicit operator containment. Does not replace a post-restore revocation ledger."""

import time
from sqlalchemy import update, delete
from olumira.extensions import db
from olumira.models import (
    User,
    AuthSession,
    AccountToken,
    DataExport,
    WorkspaceInvitation,
    EmailOutbox,
)
from services.database import transaction


def revoke_access_artifacts():
    moment = int(time.time())
    with transaction():
        db.session.execute(update(User).values(auth_version=User.auth_version + 1))
        db.session.execute(
            update(AuthSession)
            .where(AuthSession.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
        db.session.execute(
            update(AccountToken)
            .where(AccountToken.used_at.is_(None))
            .values(used_at=moment)
        )
        db.session.execute(delete(DataExport))
        db.session.execute(
            update(WorkspaceInvitation)
            .where(WorkspaceInvitation.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
        db.session.execute(
            update(EmailOutbox)
            .where(EmailOutbox.delivered_at.is_(None))
            .values(cancelled_at=moment, encrypted_payload="")
        )
