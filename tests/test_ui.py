"""UI workflow regressions against a temporary database, never the demo database."""
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import database


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.database_patch = patch.object(database, 'DATABASE', str(Path(cls.temp.name) / 'test.db'))
        cls.database_patch.start()
        cls.module = importlib.import_module('app')
        cls.module.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.database_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.owner = session['owner_id']

    def test_pages_and_active_navigation(self):
        for route, endpoint in [('/', 'dashboard'), ('/routines', 'routines'), ('/communication', 'communication'), ('/observations', 'observations'), ('/resources', 'resources')]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertEqual(html.count('aria-current="page"'), 1)
                self.assertIn('Skip to content', html)
                self.assertIn('id="primary-links"', html)

    def test_completion_shared_between_pages_and_owners(self):
        routine = self.module.get_routines(self.owner)[0]
        path = f'/routines/{routine["id"]}/toggle'
        self.assertEqual(self.client.post(path).status_code, 302)
        for route in ['/', '/routines']:
            self.assertIn('aria-pressed="true"', self.client.get(route).get_data(as_text=True))
        self.assertIn('20<small>%', self.client.get('/').get_data(as_text=True))
        other = self.module.app.test_client()
        self.assertEqual(other.post(path).status_code, 404)
        self.client.post(path)
        self.assertEqual(self.module.get_routines(self.owner)[0]['completed'], 0)

    def test_routine_management(self):
        self.client.post('/routines/add', data={'name': 'Test walk', 'category': 'Afternoon'})
        routine = self.module.get_routines(self.owner)[-1]
        self.client.post(f'/routines/{routine["id"]}/edit', data={'name': 'Short walk', 'category': 'Afternoon'})
        self.assertIn('Short walk', self.client.get('/routines').get_data(as_text=True))
        self.client.post(f'/routines/{routine["id"]}/delete')
        self.assertNotIn('Short walk', self.client.get('/routines').get_data(as_text=True))
        self.client.post('/routines/add-template', data={'template': 'Bedtime'})
        self.assertIn('Lights out', self.client.get('/routines').get_data(as_text=True))

    def test_observation_updates_dashboard_and_escapes_html(self):
        response = self.client.post('/observations', data={'activity': '<script>test</script>', 'date': database.today_string(), 'notes': 'A fictional test observation', 'mood': 'Calm', 'tags': 'test'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('&lt;script&gt;test&lt;/script&gt;', html)
        self.assertIn('A fictional test observation', html)
        self.assertIn('<strong>1</strong>', html)
        other = self.module.app.test_client()
        self.assertNotIn('A fictional test observation', other.get('/').get_data(as_text=True))

    def test_dashboard_links_and_local_artwork(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertEqual(html.count('class="action-button"'), 4)
        with self.client.get('/static/images/welcome-garden.svg') as artwork:
            self.assertEqual(artwork.status_code, 200)
        self.assertIn('No observations yet', html)


if __name__ == '__main__':
    unittest.main()
