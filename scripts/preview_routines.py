"""Disposable, loopback-only fictional demo. Never opens the real application DB."""

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flask import session
from flask_login import login_user
from flask_migrate import upgrade
from sqlalchemy import select
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    User,
    FamilyWorkspace,
    CareProfile,
    WorkspaceMembership,
    Routine,
    RoutineCompletion,
    Observation,
    EmailOutbox,
)
from services.authentication import register_user
from services.account_recovery import request_link, verify_email
from services.email_delivery import cipher
from services.database import transaction, today_string
from services.workspaces import create_workspace, resolve_context
from services import (
    routine_builder as builder,
    routine_scheduling as scheduling,
    routine_sessions as runs,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5053)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    origin = f"http://127.0.0.1:{args.port}"
    with tempfile.TemporaryDirectory(prefix="olumira-day24-fictional-") as directory:
        app = create_app(
            {
                "APP_ENV": "development",
                "DATABASE": str(Path(directory) / "preview.db"),
                "DATABASE_URL": None,
                "SECRET_KEY": secrets.token_urlsafe(48),
                "SESSION_COOKIE_NAME": f"olumira_day24_preview_{args.port}",
                "PUBLIC_APP_URL": origin,
                "MAIL_BACKEND": "development",
                "TRUSTED_HOSTS": ["127.0.0.1", "localhost"],
            }
        )
        password = "Olumira-" + secrets.token_urlsafe(15)
        with app.app_context():
            upgrade()
            users = []
            for email, name in [
                ("preview@example.com", "Fictional Rowan"),
                ("sage-preview@example.com", "Fictional Sage"),
                ("willow-preview@example.com", "Fictional Willow"),
            ]:
                user = register_user(email, name, password)
                request_link(email, "verify_email")
                job = db.session.scalar(
                    select(EmailOutbox).where(
                        EmailOutbox.user_id == user.id,
                        EmailOutbox.kind == "verify_email",
                        EmailOutbox.cancelled_at.is_(None),
                    )
                )
                payload = json.loads(cipher().decrypt(job.encrypted_payload.encode()))
                code = re.search(r"#token=([A-Za-z0-9_-]{43})", payload["text"]).group(
                    1
                )
                assert verify_email(code) == user.id
                users.append(user)
            owner = users[0]
            owner_id = owner.id
            workspace_id = owner.owner_id
            with transaction():
                workspace = db.session.get(FamilyWorkspace, workspace_id)
                workspace.name = "Fictional Cedar Family"
                profile = CareProfile(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace.id,
                    display_name="Fictional Fern",
                    avatar="leaf",
                    communication="Offer two short choices and allow time to respond.",
                    routine_preferences="A calm start with a visual sequence.",
                    interests="Gardens and woodland stories.",
                    support_notes="Fictional demonstration only.",
                )
                db.session.add(profile)
                for user, role in [(users[1], "caregiver"), (users[2], "viewer")]:
                    db.session.add(
                        WorkspaceMembership(
                            id=uuid.uuid4().hex,
                            workspace_id=workspace.id,
                            user_id=user.id,
                            role=role,
                            status="active",
                        )
                    )
                for routine in list(
                    db.session.scalars(
                        select(Routine)
                        .where(Routine.workspace_id == workspace.id)
                        .order_by(Routine.id)
                    )
                )[:2]:
                    db.session.add(
                        RoutineCompletion(
                            routine_id=routine.id, completion_date=today_string()
                        )
                    )
                db.session.add(
                    Observation(
                        owner_id=workspace.id,
                        workspace_id=workspace.id,
                        activity="Fictional calm morning",
                        date=today_string(),
                        notes="Demo only: a relaxed start with a visual sequence.",
                        mood="Calm",
                        tags="Fictional demo",
                    )
                )
                create_workspace(owner_id, "Fictional Willow Family")
                profile_id = profile.id
            with app.test_request_context("/"):
                login_user(db.session.get(User, owner_id))
                session["workspace_id"] = workspace_id
                for chosen, title in [
                    (None, "Fictional gentle morning"),
                    (profile_id, "Fictional Fern’s forest morning"),
                ]:
                    session["profile_id"] = chosen
                    resolve_context()
                    values = dict(
                        name=title,
                        description="A calm five-step sequence. Fictional preview only.",
                        category="Morning",
                        icon="sun",
                        color="sage" if chosen else "peach",
                        profile_id=chosen or "",
                        steps=[
                            dict(
                                id="",
                                title=t,
                                description="Take this step at your own pace.",
                                icon="sun" if i < 3 else "book",
                            )
                            for i, t in enumerate(
                                [
                                    "Wake up gently",
                                    "Choose clothes",
                                    "Share breakfast",
                                    "Choose a story",
                                    "Check the day ahead",
                                ]
                            )
                        ],
                    )
                    rid, _ = builder.save(values)
                    day = scheduling.utcnow().astimezone(
                        scheduling.zone("America/Chicago")
                    ).date() + timedelta(days=1)
                    while day.weekday() > 4:
                        day += timedelta(days=1)
                    scheduling.save(
                        rid,
                        dict(
                            timezone="America/Chicago",
                            local_time="07:30",
                            frequency="weekdays",
                            weekdays=["0", "1", "2", "3", "4"],
                            start_date=day.isoformat(),
                            end_date="",
                        ),
                    )
                    run_id = runs.start(rid, uuid.uuid4().hex)
                    for step in runs.steps_for(run_id)[:3]:
                        run = runs.find(run_id)
                        runs.mutate(
                            run_id, "complete", run.version, uuid.uuid4().hex, step.id
                        )
                    run = runs.find(run_id)
                    runs.mutate(run_id, "pause", run.version, uuid.uuid4().hex)
        access = (
            Path(tempfile.gettempdir())
            / f"olumira-day24-preview-{args.port}-access.json"
        )
        descriptor = os.open(access, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(
                dict(
                    url=origin + "/auth/login",
                    email="preview@example.com",
                    caregiver="sage-preview@example.com",
                    viewer="willow-preview@example.com",
                    password=password,
                ),
                handle,
            )
        print(
            f"Fictional preview: {origin}/auth/login\nPrivate demo credentials: {access}\nChanges last until this process stops. Real application data is untouched.",
            flush=True,
        )
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
