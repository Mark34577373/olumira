"""Populated communication data survives both additive milestone migrations."""

import tempfile, unittest, uuid
from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from flask_migrate import upgrade
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    CareProfile,
    CommunicationBoard,
    CommunicationCard,
    CommunicationPreference,
    FavoriteCommunicationCard,
)
from support import create_user


class PersonalizationCareMigrationTests(unittest.TestCase):
    def test_populated_0011_0012_preserved_and_reference_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                {"APP_ENV": "testing", "DATABASE": str(Path(directory) / "upgrade.db")}
            )
            with app.app_context():
                upgrade(revision="0011")
            uid, workspace = create_user(app, "fictional-day28-migration@example.com")
            with app.app_context():
                profile = CareProfile(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace,
                    display_name="Fictional Fern",
                )
                db.session.add(profile)
                db.session.flush()
                board = CommunicationBoard(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace,
                    profile_id=profile.id,
                    created_by=uid,
                    title="Fictional preserved board",
                    description="",
                    category="Needs",
                    layout="2",
                    version=1,
                )
                db.session.add(board)
                db.session.flush()
                card = CommunicationCard(
                    id=uuid.uuid4().hex,
                    board_id=board.id,
                    label="Water",
                    spoken_text="Water",
                    symbol="water",
                    color="sage",
                    position=0,
                )
                db.session.add(card)
                db.session.commit()

                def snapshot():
                    with db.engine.connect() as connection:
                        return {
                            name: sorted(
                                [
                                    tuple(row)
                                    for row in connection.execute(
                                        text('SELECT * FROM "' + name + '"')
                                    )
                                ],
                                key=repr,
                            )
                            for name in inspect(connection).get_table_names()
                            if name not in {"alembic_version", "sqlite_sequence"}
                        }

                before = snapshot()
                upgrade(revision="0012")
                after = snapshot()
                self.assertEqual(before, {n: after[n] for n in before})
                pref = CommunicationPreference(
                    profile_id=profile.id,
                    workspace_id=workspace,
                    default_board_id=board.id,
                )
                db.session.add(pref)
                db.session.flush()
                db.session.add(
                    FavoriteCommunicationCard(
                        profile_id=profile.id,
                        workspace_id=workspace,
                        card_id=card.id,
                        position=0,
                    )
                )
                db.session.commit()
                before = snapshot()
                upgrade()
                upgrade()
                after = snapshot()
                self.assertEqual(before, {n: after[n] for n in before})
                with db.engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text("PRAGMA integrity_check")).scalar(),
                        "ok",
                    )
                    self.assertEqual(
                        connection.execute(text("PRAGMA foreign_key_check")).all(), []
                    )
                    self.assertEqual(
                        compare_metadata(
                            MigrationContext.configure(connection), db.metadata
                        ),
                        [],
                    )
                db.session.remove()
                db.engine.dispose()
