"""Private board and phrase workflows with genuine CSRF and shared permissions."""

import concurrent.futures
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    CommunicationBoard as Board,
    CommunicationCard as Card,
    SavedCommunicationPhrase as Phrase,
    CareProfile,
    WorkspaceMembership,
)
from support import create_user, login, post, csrf_token


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(self.temp.name) / "boards.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with self.app.app_context():
            upgrade()
        self.uid, self.ws = create_user(self.app, "fiction-board@example.com")
        self.other, self.otherws = create_user(
            self.app, "fiction-other-board@example.com"
        )
        self.client = self.app.test_client()
        login(self.client, "fiction-board@example.com")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def values(self, **changes):
        values = dict(
            scope_workspace=self.ws,
            title="Fictional Basic Needs",
            description="Fictional only",
            category="Basic needs",
            layout="3",
            profile_id="",
            version="",
            creation_key=uuid.uuid4().hex,
            card_id=["", "", ""],
            card_label=["I", "want", "water"],
            card_spoken_text=["I", "want", "water"],
            card_symbol=["person", "want", "water"],
            card_color=["sage", "peach", "sky"],
        )
        values.update(changes)
        values["scope_workspace"] = self.ws
        return values

    def create(self, **changes):
        response = post(self.client, "/communication/new", self.values(**changes))
        self.assertEqual(response.status_code, 302, response.text)
        return response.location.rsplit("/", 1)[1]

    def edit_values(self, bid, **changes):
        from services.communication import draft

        with self.app.test_request_context("/"):
            from flask import g

            g.profile_id = None
            values = draft(db.session.get(Board, bid))
        cards = values.pop("cards")
        for key in ["id", "label", "spoken_text", "symbol", "color"]:
            values["card_" + key] = [c[key] for c in cards]
        values.update(changes)
        values["scope_workspace"] = self.ws
        return values

    def shared(self, role):
        with self.app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id=uuid.uuid4().hex,
                    workspace_id=self.ws,
                    user_id=self.other,
                    role=role,
                    status="active",
                )
            )
            db.session.commit()
        client = self.app.test_client()
        login(client, "fiction-other-board@example.com")
        with client.session_transaction() as context:
            context["workspace_id"] = self.ws
        return client

    def test_library_templates_and_separate_board_view(self):
        for name in ["needs", "feelings", "activities", "words"]:
            page = self.client.get("/communication/new?template=" + name)
            self.assertEqual(page.status_code, 200, page.text)
            self.assertEqual(
                page.text.count("data-card-editor"), 7
            )  # six rows plus the inert template
        bid = self.create()
        page = self.client.get("/communication/" + bid)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertNotIn("data-card-editor", page.text)
        self.assertNotIn("Edit board", page.text)
        self.assertIn("Fictional Basic Needs", self.client.get("/communication").text)
        self.assertIn(
            'id="communication-app"', self.client.get("/communication/quick").text
        )

    def test_card_create_edit_reorder_remove_duplicate_persist(self):
        bid = self.create()
        values = self.edit_values(bid)
        for field in ["id", "label", "spoken_text", "symbol", "color"]:
            values["card_" + field] = list(reversed(values["card_" + field]))
        values["card_label"][0] = "Water please"
        values["card_spoken_text"][0] = "I need water."
        for field, val in dict(
            id="",
            label="Help",
            spoken_text="Help please.",
            symbol="help",
            color="lavender",
        ).items():
            values["card_" + field].append(val)
        self.assertEqual(
            post(self.client, f"/communication/{bid}/edit", values).status_code, 302
        )
        with self.app.app_context():
            cards = list(
                db.session.scalars(
                    select(Card).where(Card.board_id == bid).order_by(Card.position)
                )
            )
            self.assertEqual(
                [c.label for c in cards], ["Water please", "want", "I", "Help"]
            )
            self.assertEqual([c.position for c in cards], [0, 1, 2, 3])
        values = self.edit_values(bid)
        for field in ["id", "label", "spoken_text", "symbol", "color"]:
            values["card_" + field].pop(1)
        self.assertEqual(
            post(self.client, f"/communication/{bid}/edit", values).status_code, 302
        )
        native = post(
            self.client,
            f"/communication/{bid}/edit",
            dict(self.edit_values(bid), editor_action="copy:0"),
        )
        self.assertEqual(native.status_code, 200)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(Card).where(Card.board_id == bid)
                ),
                3,
            )

    def test_duplicate_archive_restore_and_idempotent_creation(self):
        values = self.values()
        first = post(self.client, "/communication/new", values)
        self.assertEqual(
            post(self.client, "/communication/new", values).location, first.location
        )
        bid = first.location.rsplit("/", 1)[1]
        duplicated = post(
            self.client,
            f"/communication/{bid}/manage/duplicate",
            dict(version="1", profile_id="", creation_key=uuid.uuid4().hex),
        )
        self.assertEqual(duplicated.status_code, 302)
        self.assertEqual(
            post(
                self.client, f"/communication/{bid}/manage/archive", dict(version="1")
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get(f"/communication/{bid}/edit").status_code, 409)
        self.assertIn("archived", self.client.get("/communication/" + bid).text)
        self.assertEqual(
            post(
                self.client, f"/communication/{bid}/manage/restore", dict(version="2")
            ).status_code,
            302,
        )
        with self.app.app_context():
            boards = list(db.session.scalars(select(Board)))
            self.assertEqual(len(boards), 2)
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Card)), 6
            )

    def test_validation_foreign_ids_stale_draft_and_escaping(self):
        bid = self.create()
        other = self.create(title="Other board")
        stale = self.edit_values(bid)
        valid = dict(stale, title="Fictional changed")
        self.assertEqual(
            post(self.client, f"/communication/{bid}/edit", valid).status_code, 302
        )
        conflict = post(
            self.client,
            f"/communication/{bid}/edit",
            dict(stale, title="Retained draft"),
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("Retained draft", conflict.text)
        for changes in [
            dict(title=""),
            dict(layout="100"),
            dict(card_label=[""]),
            dict(card_symbol=["invalid"] * 3),
            dict(card_id=["same"] * 3),
            dict(card_spoken_text=["x" * 201] * 3),
        ]:
            self.assertEqual(
                post(
                    self.client, "/communication/new", self.values(**changes)
                ).status_code,
                422,
            )
        foreign = self.edit_values(bid)
        foreign["card_id"][0] = self.edit_values(other)["card_id"][0]
        self.assertEqual(
            post(self.client, f"/communication/{bid}/edit", foreign).status_code, 404
        )
        escaped = self.create(title="<script>fiction</script>")
        self.assertNotIn(
            "<script>fiction</script>",
            self.client.get("/communication/" + escaped).text,
        )

    def test_profile_and_family_scope_and_database_guard(self):
        profile = uuid.uuid4().hex
        foreign = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add_all(
                [
                    CareProfile(
                        id=profile, workspace_id=self.ws, display_name="Fictional Fern"
                    ),
                    CareProfile(
                        id=foreign,
                        workspace_id=self.otherws,
                        display_name="Fictional Other",
                    ),
                ]
            )
            db.session.commit()
        self.assertEqual(
            post(
                self.client, "/communication/new", self.values(profile_id=foreign)
            ).status_code,
            404,
        )
        bid = self.create(profile_id=profile)
        self.assertEqual(self.client.get("/communication/" + bid).status_code, 200)
        with self.client.session_transaction() as context:
            context.pop("profile_id", None)
        self.assertEqual(self.client.get("/communication/" + bid).status_code, 404)
        with self.app.app_context():
            with self.assertRaises(IntegrityError):
                db.session.execute(
                    text("UPDATE communication_boards SET profile_id=:p WHERE id=:b"),
                    dict(p=foreign, b=bid),
                )
                db.session.commit()
            db.session.rollback()
        other = self.app.test_client()
        login(other, "fiction-other-board@example.com")
        self.assertEqual(other.get("/communication/" + bid).status_code, 404)

    def test_viewer_caregiver_csrf_and_revoked_access(self):
        bid = self.create()
        viewer = self.shared("viewer")
        self.assertEqual(viewer.get("/communication/" + bid).status_code, 200)
        for path, data in [
            ("/communication/new", self.values()),
            (f"/communication/{bid}/edit", self.edit_values(bid)),
            (f"/communication/{bid}/manage/archive", dict(version="1")),
        ]:
            self.assertEqual(post(viewer, path, data).status_code, 403)
            self.assertEqual(self.client.post(path, data=data).status_code, 400)
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == self.other,
                )
            )
            member_id = member.id
            member.role = "caregiver"
            db.session.commit()
        self.assertEqual(
            post(
                viewer,
                f"/communication/{bid}/edit",
                self.edit_values(bid, title="Shared edit"),
            ).status_code,
            302,
        )
        with self.app.app_context():
            member = db.session.get(WorkspaceMembership, member_id)
            member.status = "revoked"
            db.session.commit()
        self.assertEqual(viewer.get("/communication/" + bid).status_code, 404)

    def test_native_draft_actions_and_failed_save_rollback(self):
        values = self.values()
        for action in ["add", "up:1", "down:0", "copy:0", "remove:0", "preview"]:
            response = post(
                self.client, "/communication/new", dict(values, editor_action=action)
            )
            self.assertEqual(response.status_code, 200, response.text)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Board)), 0
            )
        with patch(
            "services.communication.care_audit",
            side_effect=RuntimeError("Fictional failure"),
        ):
            with self.assertRaises(RuntimeError):
                post(self.client, "/communication/new", values)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Board)), 0
            )
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Card)), 0
            )

    def test_search_filters_and_empty_board(self):
        bid = self.create(
            card_id=[],
            card_label=[],
            card_spoken_text=[],
            card_symbol=[],
            card_color=[],
        )
        self.assertIn("no cards", self.client.get("/communication/" + bid).text)
        self.assertNotIn(
            "Fictional Basic Needs", self.client.get("/communication?q=unmatched").text
        )
        for path in [
            "/communication?page=0",
            "/communication?status=unknown",
            "/communication?page=bad",
        ]:
            self.assertEqual(self.client.get(path).status_code, 400)

    def phrase_values(self, **changes):
        values = dict(
            label="Water please",
            text="I want water.",
            creation_key=uuid.uuid4().hex,
            scope_workspace=self.ws,
            scope_profile="",
        )
        values.update(changes)
        return values

    def test_saved_phrase_crud_order_archive_restore_and_idempotency(self):
        data = self.phrase_values()
        first = post(
            self.client,
            "/communication/phrases",
            data,
            headers={"Accept": "application/json"},
        )
        self.assertEqual(first.status_code, 201, first.text)
        identity = first.json["id"]
        repeated = post(
            self.client,
            "/communication/phrases",
            dict(data, text="Changed retry"),
            headers={"Accept": "application/json"},
        )
        self.assertEqual(repeated.json["text"], "I want water.")
        second = post(
            self.client,
            "/communication/phrases",
            self.phrase_values(label="A break", text="I want a break."),
            headers={"Accept": "application/json"},
        ).json["id"]
        self.assertEqual(
            post(
                self.client,
                f"/communication/phrases/{identity}/edit",
                self.phrase_values(label="Help", text="I need help.", version="1"),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client,
                f"/communication/phrases/{identity}/edit",
                self.phrase_values(version="1"),
            ).status_code,
            409,
        )
        self.assertEqual(
            post(
                self.client, f"/communication/phrases/{second}/up", dict(version="1")
            ).status_code,
            302,
        )
        with self.app.app_context():
            ordered = list(db.session.scalars(select(Phrase).order_by(Phrase.position)))
            self.assertEqual(ordered[0].id, second)
            current = db.session.get(Phrase, identity).version
        self.assertEqual(
            post(
                self.client,
                f"/communication/phrases/{identity}/archive",
                dict(version=current),
            ).status_code,
            302,
        )
        with self.app.app_context():
            current = db.session.get(Phrase, identity).version
        self.assertEqual(
            post(
                self.client,
                f"/communication/phrases/{identity}/restore",
                dict(version=current),
            ).status_code,
            302,
        )
        bid = self.create()
        page = self.client.get("/communication/" + bid)
        self.assertIn("I need help.", page.text)
        self.assertIn("A break", page.text)

    def test_phrase_scope_roles_validation_csrf_and_rollback(self):
        result = post(
            self.client,
            "/communication/phrases",
            self.phrase_values(),
            headers={"Accept": "application/json"},
        )
        identity = result.json["id"]
        viewer = self.shared("viewer")
        self.assertEqual(
            post(viewer, "/communication/phrases", self.phrase_values()).status_code,
            403,
        )
        self.assertEqual(
            post(
                viewer, f"/communication/phrases/{identity}/archive", dict(version="1")
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/communication/phrases", data=self.phrase_values()
            ).status_code,
            400,
        )
        self.assertEqual(
            post(
                self.client, "/communication/phrases", self.phrase_values(text="")
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/communication/phrases",
                self.phrase_values(text="x" * 1001),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/communication/phrases",
                self.phrase_values(scope_profile="foreign"),
                headers={"Accept": "application/json"},
            ).status_code,
            409,
        )
        with viewer.session_transaction() as context:
            context["workspace_id"] = self.otherws
        self.assertEqual(
            post(
                viewer, f"/communication/phrases/{identity}/archive", dict(version="1")
            ).status_code,
            404,
        )
        self.assertNotIn("I want water.", viewer.get("/communication/phrases").text)
        with patch(
            "services.communication.care_audit",
            side_effect=RuntimeError("fictional failure"),
        ):
            with self.assertRaises(RuntimeError):
                post(
                    self.client,
                    "/communication/phrases",
                    self.phrase_values(label="Not saved"),
                )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Phrase)), 1
            )

    def test_profile_phrases_not_shared_with_workspace_boards(self):
        profile = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile, workspace_id=self.ws, display_name="Fictional Fern"
                )
            )
            db.session.commit()
        workspace_board = self.create()
        with self.client.session_transaction() as context:
            context["profile_id"] = profile
        self.assertEqual(
            post(
                self.client,
                "/communication/phrases",
                self.phrase_values(scope_profile=profile),
            ).status_code,
            302,
        )
        profile_board = self.create(profile_id=profile)
        self.assertIn(
            "Water please", self.client.get("/communication/" + profile_board).text
        )
        with self.client.session_transaction() as context:
            context.pop("profile_id", None)
        self.assertNotIn(
            "Water please", self.client.get("/communication/" + workspace_board).text
        )

    def test_simultaneous_board_edits_preserve_one_complete_version(self):
        bid = self.create()
        helper = self.shared("caregiver")
        values = self.edit_values(bid)
        tokens = [csrf_token(c) for c in [self.client, helper]]

        def save(pair):
            client, token = pair
            return client.post(
                f"/communication/{bid}/edit",
                data=dict(values, csrf_token=token, title="Fictional shared update"),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(save, zip([self.client, helper], tokens)))
        self.assertEqual(sorted(r.status_code for r in responses), [302, 409])
        with self.app.app_context():
            self.assertEqual(db.session.get(Board, bid).version, 2)
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(Card).where(Card.board_id == bid)
                ),
                3,
            )
