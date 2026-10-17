"""Day 27 persistence, cross-profile defaults and reference favorites."""

import uuid, unittest
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    CareProfile,
    CommunicationPreference,
    FavoriteCommunicationCard,
    FavoriteCommunicationPhrase,
)
import test_communication as fixtures
from support import post, login


class PersonalizationTests(unittest.TestCase):
    tearDown = fixtures.CommunicationTests.tearDown
    values = fixtures.CommunicationTests.values
    create = fixtures.CommunicationTests.create
    edit_values = fixtures.CommunicationTests.edit_values
    shared = fixtures.CommunicationTests.shared
    phrase_values = fixtures.CommunicationTests.phrase_values

    # Reuse the existing fixture/forms; inherited board regression tests stay relevant.
    def setUp(self):
        fixtures.CommunicationTests.setUp(self)
        self.profile = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=self.profile, workspace_id=self.ws, display_name="Fictional Fern"
                )
            )
            db.session.commit()
        with self.client.session_transaction() as context:
            context["profile_id"] = self.profile

    def pref_values(self, **changes):
        values = dict(
            scope_workspace=self.ws,
            scope_profile=self.profile,
            version="0",
            card_size="large",
            layout="2",
            text_position="above",
            show_text="on",
            show_symbols="on",
            speech_enabled="on",
            speech_rate="0.8",
            voice_id="fiction-local",
            simplified="on",
            high_contrast="on",
            reduced_motion="on",
            default_board_id="",
        )
        values.update(changes)
        return values

    def test_preferences_default_board_persist_and_layout(self):
        bid = self.create(profile_id=self.profile)
        saved = post(
            self.client,
            "/communication/settings",
            self.pref_values(default_board_id=bid),
        )
        self.assertEqual(saved.status_code, 302, saved.text)
        self.assertEqual(
            self.client.get("/communication/open").location, f"/communication/{bid}"
        )
        page = self.client.get("/communication/" + bid)
        self.assertEqual(page.status_code, 200)
        self.assertIn("pref-size-large", page.text)
        self.assertIn("pref-high-contrast", page.text)
        self.assertIn('data-speech-rate="0.8"', page.text)
        login(self.client, "fiction-board@example.com")
        with self.client.session_transaction() as context:
            context["profile_id"] = self.profile
        self.assertIn(
            'value="fiction-local"', self.client.get("/communication/settings").text
        )
        self.assertEqual(
            post(
                self.client, "/communication/settings", self.pref_values(version="0")
            ).status_code,
            409,
        )

    def test_favorites_idempotent_order_scope_and_archived_sources(self):
        bid = self.create(profile_id=self.profile)
        cards = self.edit_values(bid)["card_id"]

        def action(kind, target, verb, version):
            return post(
                self.client,
                f"/communication/favorites/{kind}/{target}/{verb}",
                dict(
                    scope_workspace=self.ws, scope_profile=self.profile, version=version
                ),
            )

        self.assertEqual(action("card", cards[0], "add", 0).status_code, 302)
        self.assertEqual(action("card", cards[0], "add", 0).status_code, 302)
        self.assertEqual(action("card", cards[1], "add", 1).status_code, 302)
        self.assertEqual(action("card", cards[1], "up", 2).status_code, 302)
        phrase = post(
            self.client,
            "/communication/phrases",
            self.phrase_values(scope_profile=self.profile),
            headers={"Accept": "application/json"},
        ).json["id"]
        self.assertEqual(action("phrase", phrase, "add", 3).status_code, 302)
        page = self.client.get("/communication/favorites")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("Water please", page.text)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(FavoriteCommunicationCard)
                ),
                2,
            )
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(FavoriteCommunicationPhrase)
                ),
                1,
            )
        phrase2 = post(
            self.client,
            "/communication/phrases",
            self.phrase_values(
                scope_profile=self.profile, label="Break", text="A break please"
            ),
            headers={"Accept": "application/json"},
        ).json["id"]
        self.assertEqual(action("phrase", phrase2, "add", 4).status_code, 302)
        self.assertEqual(action("phrase", phrase2, "up", 5).status_code, 302)
        page = self.client.get("/communication/favorites").text
        self.assertLess(
            page.index('data-phrase-id="' + phrase2 + '"'),
            page.index('data-phrase-id="' + phrase + '"'),
        )
        before_hash = self.client.get("/communication/favorites/state").json["version"]
        self.assertEqual(
            post(
                self.client, f"/communication/{bid}/manage/archive", dict(version="1")
            ).status_code,
            302,
        )
        self.assertNotIn(
            'data-label="I"', self.client.get("/communication/favorites").text
        )
        self.assertNotEqual(
            before_hash,
            self.client.get("/communication/favorites/state").json["version"],
        )
        self.assertEqual(action("card", cards[0], "remove", 6).status_code, 302)

    def test_preferences_and_favorites_validation_and_viewer(self):
        bid = self.create(profile_id=self.profile)
        cid = self.edit_values(bid)["card_id"][0]
        self.assertEqual(
            post(
                self.client,
                "/communication/settings",
                self.pref_values(show_symbols="", show_text=""),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/communication/settings",
                self.pref_values(card_size="giant"),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/communication/settings",
                self.pref_values(default_board_id="f" * 32),
            ).status_code,
            404,
        )
        viewer = self.shared("viewer")
        with viewer.session_transaction() as context:
            context["profile_id"] = self.profile
        self.assertEqual(
            post(viewer, "/communication/settings", self.pref_values()).status_code, 403
        )
        self.assertEqual(
            post(
                viewer,
                f"/communication/favorites/card/{cid}/add",
                dict(scope_workspace=self.ws, scope_profile=self.profile, version=0),
            ).status_code,
            403,
        )
        with self.client.session_transaction() as context:
            context.pop("profile_id", None)
        self.assertEqual(self.client.get("/communication/favorites").status_code, 200)
        self.assertNotIn(
            'data-label="I"', self.client.get("/communication/favorites").text
        )
