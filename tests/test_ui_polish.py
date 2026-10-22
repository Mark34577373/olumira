"""Confirmed checklist writes retain CSRF, exact scope and retry safety."""
import unittest
from unittest.mock import patch
from sqlalchemy import select,func
import test_communication as fixtures
from support import post
from olumira.extensions import db
from olumira.models import Routine,RoutineCompletion,RoutineCompletionSnapshot,CareProfile
from services.database import today_string


class UIPolishTests(unittest.TestCase):
    setUp=fixtures.CommunicationTests.setUp
    tearDown=fixtures.CommunicationTests.tearDown
    shared=fixtures.CommunicationTests.shared

    def item(self, workspace=None):
        with self.app.app_context():
            return db.session.scalar(select(Routine.id).where(Routine.workspace_id==(workspace or self.ws),Routine.is_checklist.is_(True)).order_by(Routine.id))

    def values(self, **changes):
        with self.app.app_context():
            day=today_string()
        values=dict(scope_workspace=self.ws,scope_profile='',checklist_date=day,completed='true',return_to='dashboard')
        values.update(changes)
        return values

    def save(self,client=None,rid=None,**changes):
        return post(client or self.client,f'/routines/{rid or self.item()}/toggle',self.values(**changes),headers={'Accept':'application/json'})

    def test_confirmed_json_state_and_idempotent_retry(self):
        rid=self.item()
        response=self.save(rid=rid)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        data=response.json
        self.assertEqual((data['completed'],data['total'],data['progress']),(1,5,20))
        self.assertEqual(data['workspace_id'],self.ws)
        self.assertEqual(data['profile_id'],'')
        self.assertTrue(next(item['completed'] for item in data['items'] if item['id']==rid))
        self.assertNotIn('name',data['items'][0])
        self.assertEqual(self.save(rid=rid).json['completed'],1)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(RoutineCompletion).where(RoutineCompletion.routine_id==rid)),1)
            self.assertEqual(db.session.scalar(select(func.count()).select_from(RoutineCompletionSnapshot).where(RoutineCompletionSnapshot.routine_id==rid)),1)
        self.assertEqual(self.save(rid=rid,completed='false').json['completed'],0)
        self.assertEqual(self.save(rid=rid,completed='false').json['completed'],0)

    def test_json_requires_csrf_explicit_state_context_and_date(self):
        path=f'/routines/{self.item()}/toggle'
        self.assertEqual(self.client.post(path,data=self.values(),headers={'Accept':'application/json'}).status_code,400)
        for changes,code in [({'completed':'toggle'},400),({'scope_workspace':self.otherws},409),({'scope_profile':'f'*32},409),({'checklist_date':'2000-01-01'},409)]:
            with self.subTest(changes=changes):
                self.assertEqual(self.save(**changes).status_code,code)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(RoutineCompletion)),0)

    def test_foreign_id_viewer_and_profile_boundaries(self):
        self.assertEqual(self.save(rid=self.item(self.otherws)).status_code,404)
        viewer=self.shared('viewer')
        self.assertEqual(self.save(client=viewer).status_code,403)
        with self.app.app_context():
            db.session.add(CareProfile(id='b'*32,workspace_id=self.ws,display_name='Fictional Fern'))
            db.session.commit()
        with self.client.session_transaction() as session:
            session['profile_id']='b'*32
        self.assertEqual(self.save(scope_profile='b'*32).status_code,404)

    def test_native_form_remains_working_and_repeated_desired_write_is_safe(self):
        path=f'/routines/{self.item()}/toggle'
        for _ in range(2):
            response=post(self.client,path,self.values())
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.location,'/')
        self.assertIn('aria-pressed="true"',self.client.get('/').text)
        # The existing routine-library toggle contract is unchanged.
        self.assertEqual(post(self.client,path,{'return_to':'routines'}).location,'/routines')
        self.assertIn('0<small>%',self.client.get('/').text)

    def test_date_change_inside_transaction_and_write_failure_do_not_report_success(self):
        values=self.values()
        with patch('services.routines.today_string',return_value='2000-01-01'):
            response=post(self.client,f'/routines/{self.item()}/toggle',values,headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,409)
        with patch('services.routines.care_audit',side_effect=ValueError('Fictional rejected write')):
            self.assertEqual(self.save().status_code,409)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(RoutineCompletion)),0)

    def test_global_context_and_six_real_quick_actions(self):
        html=self.client.get('/').text
        self.assertIn('ACTIVE CARE CONTEXT',html)
        self.assertIn('Choose an option, then switch to apply it.',html)
        self.assertIn('Open care plans →',html)
        self.assertEqual(html.count('class="action-button"'),6)
        self.assertIn('data-checklist',html)
        self.assertIn('data-motion-toggle',html)
