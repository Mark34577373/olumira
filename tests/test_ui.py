"""UI workflow regressions against a temporary database, never the demo database."""
import tempfile
import unittest
from pathlib import Path

from flask_migrate import upgrade


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        from olumira import create_app
        from services.routines import get_routines
        cls.app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(cls.temp.name) / 'test.db')})
        with cls.app.app_context():
            upgrade()
        cls.get_routines = staticmethod(get_routines)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.owner = session['owner_id']

    def routines(self):
        with self.app.app_context():
            return self.get_routines(self.owner)

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
        routine = self.routines()[0]
        path = f'/routines/{routine["id"]}/toggle'
        self.assertEqual(self.client.post(path).status_code, 302)
        for route in ['/', '/routines']:
            self.assertIn('aria-pressed="true"', self.client.get(route).get_data(as_text=True))
        self.assertIn('20<small>%', self.client.get('/').get_data(as_text=True))
        other = self.app.test_client()
        self.assertEqual(other.post(path).status_code, 404)
        self.client.post(path)
        self.assertEqual(self.routines()[0]['completed'], 0)

    def test_routine_management(self):
        self.client.post('/routines/add', data={'name': 'Test walk', 'category': 'Afternoon'})
        routine = self.routines()[-1]
        self.client.post(f'/routines/{routine["id"]}/edit', data={'name': 'Short walk', 'category': 'Afternoon'})
        self.assertIn('Short walk', self.client.get('/routines').get_data(as_text=True))
        self.client.post(f'/routines/{routine["id"]}/delete')
        self.assertNotIn('Short walk', self.client.get('/routines').get_data(as_text=True))
        self.client.post('/routines/add-template', data={'template': 'Bedtime'})
        self.assertIn('Lights out', self.client.get('/routines').get_data(as_text=True))

    def test_observation_updates_dashboard_and_escapes_html(self):
        response = self.client.post('/observations', data={'activity': '<script>test</script>', 'date': '2026-10-16', 'notes': 'A fictional test observation', 'mood': 'Calm', 'tags': 'test'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('&lt;script&gt;test&lt;/script&gt;', html)
        self.assertIn('A fictional test observation', html)
        self.assertIn('<strong>1</strong>', html)
        other = self.app.test_client()
        self.assertNotIn('A fictional test observation', other.get('/').get_data(as_text=True))

    def test_dashboard_links_and_local_artwork(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertEqual(html.count('class="action-button"'), 4)
        with self.client.get('/static/images/welcome-garden.svg') as artwork:
            self.assertEqual(artwork.status_code, 200)
        self.assertIn('No observations yet', html)

    def test_invalid_observation_keeps_input_and_reports_error(self):
        response = self.client.post('/observations', data={'activity': 'Fictional retained input', 'date': '2026-02-30', 'notes': 'Keep these notes'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('role="alert"', response.text)
        self.assertIn('Fictional retained input', response.text)
        self.assertIn('Keep these notes', response.text)
        self.assertNotIn('Fictional retained input', self.client.get('/').text)

    def test_invalid_routine_does_not_change_records(self):
        before = len(self.routines())
        response = self.client.post('/routines/add', data={'name': 'x' * 81, 'category': 'General'}, follow_redirects=True)
        self.assertIn('role="alert"', response.text)
        self.assertEqual(len(self.routines()), before)


if __name__ == '__main__':
    unittest.main()
