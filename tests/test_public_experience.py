"""Public routes and secure public-to-platform transitions; fictional data only."""
import re
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
from unittest.mock import patch
from flask_migrate import upgrade
from olumira import create_app
from olumira.extensions import db
from olumira.models import CareProfile, User, WorkspaceMembership, OnboardingState
from support import create_user, login, post, PASSWORD


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.urls=[]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('href','').startswith('/'):
            self.urls.append(attrs['href'].split('#')[0])


class PublicExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.app=create_app(dict(APP_ENV='testing',DATABASE=str(Path(cls.temp.name)/'public.db'),AUTH_LOGIN_IP_LIMIT='1000 per hour',AUTH_LOGIN_ACCOUNT_LIMIT='1000 per hour',AUTH_REGISTER_LIMIT='1000 per hour'))
        with cls.app.app_context():
            upgrade()
        cls.uid,cls.wid=create_user(cls.app,'fictional-public@example.com')
        with cls.app.app_context():
            db.session.add(CareProfile(id='f'*32,workspace_id=cls.wid,display_name='FICTIONAL-PRIVATE-PROFILE-SENTINEL'))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        cls.temp.cleanup()

    def setUp(self):
        self.client=self.app.test_client()

    def test_public_pages_metadata_links_and_no_private_content(self):
        titles=set()
        for path in ('/','/welcome','/features','/how-it-works','/about','/contact','/privacy','/terms'):
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertIn('no-store',response.headers['Cache-Control'])
                self.assertIn('noindex',response.headers['X-Robots-Tag'])
                self.assertNotIn('FICTIONAL-PRIVATE-PROFILE-SENTINEL',response.text)
                self.assertNotIn('primary-links',response.text)
                self.assertIn('Log In',response.text)
                self.assertIn('Get Started',response.text)
                self.assertIn('name="description"',response.text)
                self.assertIn('property="og:title"',response.text)
                self.assertNotIn('rel="canonical"',response.text)
                if path!='/welcome':
                    title=re.search(r'<title>(.*?)</title>',response.text).group(1)
                    self.assertNotIn(title,titles)
                    titles.add(title)
                for url in set(Links(response.text).urls):
                    self.assertIn(self.client.get(url).status_code,(200,302),url)
        self.assertIn('Disallow: /',self.client.get('/robots.txt').text)

    def test_authenticated_public_pages_never_use_private_layout(self):
        login(self.client,'fictional-public@example.com')
        for path in ('/welcome','/features','/contact','/privacy'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('Open Dashboard',response.text)
            self.assertNotIn('>Get Started<',response.text)
            self.assertNotIn('FICTIONAL-PRIVATE-PROFILE-SENTINEL',response.text)
            self.assertNotIn('active-workspace',response.text)
            self.assertNotIn('fictional-public@example.com',response.text)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn('primary-links',self.client.get('/').text)
        self.assertIn('primary-links',self.client.get('/dashboard').text)

    def test_contact_honest_unavailable_validation_csrf_and_rate_limit(self):
        self.assertEqual(self.client.post('/contact',data={}).status_code,400)
        self.assertIn('<fieldset disabled>',self.client.get('/contact').text)
        response=post(self.client,'/contact',dict(name=' ',email='invalid',inquiry='wrong',message='x'*2001))
        self.assertEqual(response.status_code,422)
        response=post(self.client,'/contact',dict(name='Fictional visitor',email='fictional-contact@example.com',inquiry='beta',message='Fictional inquiry'))
        self.assertEqual(response.status_code,503)
        self.assertIn('No message was sent or saved.',response.text)
        self.assertNotIn('Fictional inquiry',response.text)
        bad=post(self.client,'/contact',dict(name='Fictional visitor',email='fictional-contact@example.com',inquiry='beta',message='Test',website='spam'))
        self.assertEqual(bad.status_code,422)
        # Fresh address independently proves a public abuse limit is applied.
        statuses=[post(self.client,'/contact',{},environ_overrides={'REMOTE_ADDR':'192.0.2.43'}).status_code for _ in range(6)]
        self.assertEqual(statuses[-1],429)

    def test_registration_gate_applies_to_get_post_and_public_ctas(self):
        self.app.config['REGISTRATION_ENABLED']=False
        try:
            page=self.client.get('/')
            self.assertIn('Beta access information',page.text)
            self.assertNotIn('>Get Started<',page.text)
            self.assertEqual(self.client.get('/auth/register').location,'/contact')
            response=post(self.client,'/auth/register',dict(email='no-created@example.com',display_name='Fictional',password=PASSWORD,confirm_password=PASSWORD))
            self.assertEqual(response.location,'/contact')
            with self.app.app_context():
                self.assertIsNone(db.session.scalar(db.select(User).where(User.email=='no-created@example.com')))
        finally:
            self.app.config['REGISTRATION_ENABLED']=True

    def test_default_login_setup_skip_returning_and_explicit_safe_destination(self):
        create_user(self.app,'fictional-journey@example.com')
        self.assertEqual(login(self.client,'fictional-journey@example.com').location,'/setup')
        page=self.client.get('/setup')
        self.assertEqual(page.status_code,200)
        self.assertIn('Welcome',page.text)
        with self.client.session_transaction() as session:
            workspace=session['workspace_id']
        response=post(self.client,'/setup',dict(step=0,version=0,scope_workspace=workspace,action='leave'))
        self.assertEqual(response.location,'/')
        self.assertIn('primary-links',self.client.get(response.location).text)
        post(self.client,'/auth/logout')
        self.assertEqual(login(self.client,'fictional-journey@example.com').location,'/')
        post(self.client,'/auth/logout')
        response=post(self.client,'/auth/login?next=/workspaces/accept',dict(email='fictional-journey@example.com',password=PASSWORD))
        self.assertEqual(response.location,'/workspaces/accept')

    def test_dashboard_protection_and_verification_precedes_intended_route(self):
        for path in ('/dashboard','/care-plans','/care/tasks','/setup','/routines','/settings/privacy'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,302,path)
            self.assertIn('/auth/login',response.location)
        uid,_=create_user(self.app,'fictional-not-verified@example.com')
        with self.app.app_context():
            db.session.get(User,uid).email_verified=False
            db.session.commit()
        response=post(self.client,'/auth/login?next=/workspaces/accept',dict(email='fictional-not-verified@example.com',password=PASSWORD))
        self.assertEqual(response.location,'/auth/verification')
        self.assertEqual(self.client.get('/dashboard').location,'/auth/verification')

    def test_no_workspace_and_legacy_setup_routing_do_not_loop(self):
        uid,wid=create_user(self.app,'fictional-no-workspace@example.com')
        with self.app.app_context():
            member=db.session.scalar(db.select(WorkspaceMembership).where(WorkspaceMembership.user_id==uid))
            member.status='revoked'
            db.session.commit()
        self.assertEqual(login(self.client,'fictional-no-workspace@example.com').location,'/workspaces')
        self.assertEqual(self.client.get('/workspaces',follow_redirects=True).status_code,200)
        post(self.client,'/auth/logout')
        uid,wid=create_user(self.app,'fictional-legacy-journey@example.com')
        with self.app.app_context():
            db.session.add(OnboardingState(user_id=uid,workspace_id=wid,legacy_exempt=True))
            db.session.commit()
        self.assertEqual(login(self.client,'fictional-legacy-journey@example.com').location,'/')
        self.assertEqual(self.client.get('/',follow_redirects=True).status_code,200)

    def test_registration_queue_failure_is_redacted_and_does_not_claim_delivery(self):
        with patch('services.account_recovery.request_link',side_effect=RuntimeError('FICTIONAL-PRIVATE-TRANSPORT-DETAIL')):
            with self.assertLogs(self.app.logger,level='WARNING') as captured:
                response=post(self.client,'/auth/register',dict(email='fictional-queue-failure@example.com',display_name='Fictional',password=PASSWORD,confirm_password=PASSWORD))
        self.assertEqual(response.location,'/auth/check-email')
        self.assertNotIn('FICTIONAL-PRIVATE-TRANSPORT-DETAIL',''.join(captured.output))
        self.assertIn('not confirmed',self.client.get(response.location).text)
        with self.client.session_transaction() as session:
            self.assertNotIn('_auth_sid',session)
        with self.app.app_context():
            user=db.session.scalar(db.select(User).where(User.email=='fictional-queue-failure@example.com'))
            self.assertFalse(user.email_verified)
