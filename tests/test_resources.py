import unittest
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Resource, ResourceBookmark
from services.resources import external_url
import test_communication as fixtures
from support import post, login


class ResourceTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def test_search_categories_detail_and_empty(self):
        self.assertEqual(self.client.get("/resources").status_code, 200)
        html = self.client.get("/resources?q=handoff").text
        self.assertIn("Shared handoff notes", html)
        self.assertNotIn("Visual Communication</h2>", html)
        self.assertIn(
            "2 matching resources", self.client.get("/resources?category=Safety").text
        )
        self.assertIn("0 matching resources", self.client.get("/resources?q=%25").text)
        self.assertIn(
            "Olumira · general organizational guide",
            self.client.get("/resources/guide-01").text,
        )
        self.assertEqual(self.client.get("/resources/missing").status_code, 404)
        with self.app.app_context():
            db.session.get(Resource, "guide-01").published = False
            db.session.commit()
        self.assertEqual(self.client.get("/resources/guide-01").status_code, 404)
        self.assertEqual(
            post(self.client, "/resources/guide-01/bookmark/save").status_code, 404
        )

    def test_bookmark_idempotence_removal_user_scope_and_csrf(self):
        for _ in range(2):
            self.assertEqual(
                post(self.client, "/resources/guide-01/bookmark/save").status_code, 302
            )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(ResourceBookmark)), 1
            )
        self.assertIn(
            "Visual Communication", self.client.get("/resources?saved=1").text
        )
        other = self.app.test_client()
        login(other, "fiction-other-board@example.com")
        self.assertIn("0 matching resources", other.get("/resources?saved=1").text)
        for _ in range(2):
            self.assertEqual(
                post(self.client, "/resources/guide-01/bookmark/remove").status_code,
                302,
            )
        self.assertIn(
            "0 matching resources", self.client.get("/resources?saved=1").text
        )
        viewer = self.shared("viewer")
        self.assertEqual(
            post(viewer, "/resources/guide-02/bookmark/save").status_code, 302
        )
        self.assertEqual(
            self.client.post("/resources/guide-01/bookmark/save").status_code, 400
        )

    def test_external_urls(self):
        self.assertEqual(
            external_url("https://example.com/guide"), "https://example.com/guide"
        )
        for value in [
            "javascript:alert(1)",
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com:8080",
            "https://example.com/\nx",
        ]:
            with self.assertRaises(ValueError):
                external_url(value)
