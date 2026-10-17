"""Both additive communication migrations preserve existing rows and board data."""

import tempfile, unittest, uuid
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from olumira import create_app
from olumira.extensions import db
from olumira.models import CommunicationBoard, CommunicationCard
from support import create_user


class CommunicationMigrationTests(unittest.TestCase):
    def test_populated_0009_and_0010_survive_upgrade_without_rewrites(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                {"APP_ENV": "testing", "DATABASE": str(Path(directory) / "migrate.db")}
            )
            with app.app_context():
                upgrade(revision="0009")
            uid, workspace = create_user(
                app, "fictional-communication-migration@example.com"
            )
            with app.app_context():

                def snapshot():
                    with db.engine.connect() as connection:
                        return {
                            name: sorted(
                                [
                                    tuple(r)
                                    for r in connection.execute(
                                        text('SELECT * FROM "' + name + '"')
                                    )
                                ],
                                key=repr,
                            )
                            for name in inspect(connection).get_table_names()
                            if name not in {"alembic_version", "sqlite_sequence"}
                        }

                before = snapshot()
                upgrade(revision="0010")
                after = snapshot()
                self.assertEqual(before, {name: after[name] for name in before})
                board = CommunicationBoard(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace,
                    created_by=uid,
                    title="Fictional preserved board",
                    description="Fictional only",
                    category="Needs",
                    layout="2",
                    version=1,
                )
                db.session.add(board)
                db.session.flush()
                db.session.add(
                    CommunicationCard(
                        id=uuid.uuid4().hex,
                        board_id=board.id,
                        label="Water",
                        spoken_text="I need water.",
                        symbol="water",
                        color="sage",
                        position=0,
                    )
                )
                db.session.commit()
                before = snapshot()
                upgrade()
                upgrade()
                after = snapshot()
                self.assertEqual(before, {name: after[name] for name in before})
                with db.engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text("PRAGMA foreign_key_check")).all(), []
                    )
                    self.assertEqual(
                        connection.execute(text("PRAGMA integrity_check")).scalar(),
                        "ok",
                    )
                    self.assertEqual(
                        compare_metadata(
                            MigrationContext.configure(connection), db.metadata
                        ),
                        [],
                    )
                db.session.remove()
                db.engine.dispose()
