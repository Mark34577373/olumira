"""Production-safe exception location diagnostics never expose private values."""
import re
from unittest.mock import patch
from sqlalchemy.exc import DBAPIError
from psycopg.errors import UndefinedTable
from test_proxy_redirects import app, get, ORIGIN, FORWARDED
from support import PASSWORD


def submit(client):
    html=get(client,'/auth/register').text
    token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',html)[1]
    return client.post('/auth/register',base_url=ORIGIN,
                       headers={**FORWARDED,'Referer':'https://olumira.onrender.com/auth/register'},
                       data=dict(display_name='PRIVATE-NAME',email='private@example.com',password=PASSWORD,confirm_password=PASSWORD,csrf_token=token))


def test_database_failure_reports_class_location_code_not_sql_values(app,caplog):
    error=DBAPIError('SELECT PRIVATE-SQL',{'private':'PRIVATE-PARAMETER'},UndefinedTable('PRIVATE-DB-MESSAGE'))
    with patch('olumira.routes.auth.register_user',side_effect=error):
        response=submit(app.test_client())
    assert response.status_code==500
    assert 'error_class=DBAPIError' in caplog.text
    assert 'db_error_class=UndefinedTable' in caplog.text and 'sqlstate=42P01' in caplog.text
    assert re.search(r'olumira/routes/auth.py:\d+:register',caplog.text)
    assert response.headers['X-Request-ID'] in caplog.text
    for secret in ('PRIVATE-SQL','PRIVATE-PARAMETER','PRIVATE-DB-MESSAGE','PRIVATE-NAME','private@example.com',PASSWORD):
        assert secret not in caplog.text and secret not in response.text
    assert '42P01' not in response.text


def test_unhandled_failure_reports_application_stack_without_exception_text(app,caplog):
    app.config['PROPAGATE_EXCEPTIONS']=False
    with patch('olumira.routes.auth.register_user',side_effect=RuntimeError('PRIVATE-ERROR')):
        response=submit(app.test_client())
    assert response.status_code==500
    assert 'error_class=RuntimeError' in caplog.text
    assert re.search(r'olumira/routes/auth.py:\d+:register',caplog.text)
    assert 'PRIVATE-ERROR' not in caplog.text and 'PRIVATE-ERROR' not in response.text
