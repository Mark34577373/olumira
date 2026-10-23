"""TLS diagnostics expose only versions, fixed modes and CA availability."""
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from types import SimpleNamespace
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine
from olumira.tls_diagnostic import report,bundle_status


def certificate():
    # Fictional unit-test CA only; never used as application trust material.
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME,'Fictional test CA')])
    now=datetime.now(timezone.utc)
    return x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def capture(url,env=None,overrides=None):
    engine=create_engine(url)
    events=[]
    app=SimpleNamespace(config={'SQLALCHEMY_ENGINE_OPTIONS':{'connect_args':overrides or {}}})
    try:
        with patch.dict('os.environ',env or {},clear=True):
            report(app,engine,lambda app,stage,status,**fields:events.append(dict(stage=stage,status=status,**fields)))
    finally:engine.dispose()
    return events


def test_bundle_metadata_no_contents_or_paths(tmp_path):
    filename=tmp_path/'PRIVATE-CA.pem';filename.write_bytes(certificate())
    assert bundle_status(str(filename))==dict(bundle_status='parsed',certificate_count=1)
    filename.write_text('PRIVATE-TOKEN')
    assert bundle_status(str(filename))['bundle_status']=='invalid_or_unreadable'
    assert bundle_status(str(tmp_path/'absent'))['bundle_status']=='missing'


def test_effective_system_roots_and_versions_are_sanitized():
    events=capture('postgresql+psycopg://PRIVATE-USER:PRIVATE-PASSWORD@PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=system')
    runtime=next(e for e in events if e['stage']=='tls_runtime')
    assert isinstance(runtime['libpq_version'],int) and runtime['psycopg_version']
    params=next(e for e in events if e['stage']=='tls_parameters')
    assert params['sslmode']=='verify-full' and params['hostname_verification_required']
    assert params['root_source']=='system' and not params['sqlalchemy_tls_override']
    assert 'PRIVATE-' not in json.dumps(events)
    assert all(e.get('authoritative_for_libpq') is False for e in events if e['stage']=='python_trust_hint')


def test_query_wins_over_pg_environment_but_engine_override_is_reported(tmp_path):
    path=tmp_path/'PRIVATE-ROOT.pem';path.write_bytes(certificate())
    events=capture('postgresql+psycopg://PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=system',
                   env={'PGSSLROOTCERT':'PRIVATE-ENV-ROOT','PGSSLMODE':'disable'},
                   overrides={'sslrootcert':str(path)})
    params=next(e for e in events if e['stage']=='tls_parameters')
    assert params['root_source']=='file' and params['sqlalchemy_tls_override']
    assert params['sslmode']=='verify-full' and params['pgsslrootcert_configured']
    assert next(e for e in events if e['stage']=='tls_root_bundle')['certificate_count']==1
    assert 'PRIVATE-' not in json.dumps(events)


def test_environment_fallback_and_untrusted_ca_path_never_logged():
    events=capture('postgresql+psycopg://PRIVATE-HOST/db?sslmode=verify-full',env={'PGSSLROOTCERT':'/PRIVATE-PATH/absent.pem'})
    assert next(e for e in events if e['stage']=='tls_parameters')['root_source']=='file'
    assert next(e for e in events if e['stage']=='tls_root_bundle')['bundle_status']=='missing'
    assert 'PRIVATE-' not in json.dumps(events)


def test_libpq_system_support_is_version_based():
    with patch('psycopg.pq.version',return_value=150000):
        events=capture('postgresql+psycopg://PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=system')
    assert next(e for e in events if e['stage']=='tls_runtime')['system_roots_supported'] is False


def test_query_root_precedence_and_environment_flags_without_paths():
    events=capture('postgresql+psycopg://PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=system',
                   env={'PGSSLROOTCERT':'/PRIVATE-OLD-ROOT','SSL_CERT_FILE':'/PRIVATE-CA-FILE','SSL_CERT_DIR':'/PRIVATE-CA-DIR'})
    params=next(e for e in events if e['stage']=='tls_parameters')
    assert params['root_source']=='system' and params['ssl_cert_file_configured'] and params['ssl_cert_dir_configured']
    assert next(e for e in events if e['stage']=='configured_ssl_cert_file')['bundle_status']=='missing'
    assert 'PRIVATE-' not in json.dumps(events)


def test_tls_failure_details_do_not_return_error_content():
    from olumira.tls_diagnostic import failure_detail
    from olumira.database_diagnostic import connection_status
    assert failure_detail(Exception('root certificate file PRIVATE-FILE does not exist'))=='root_file_missing'
    assert failure_detail(Exception('certificate verify failed PRIVATE-HOST: certificate has expired'))=='certificate_expired'
    assert failure_detail(Exception('PRIVATE-RAW-MESSAGE'))=='verification_failed_unspecified'
    assert connection_status(Exception('certificate has expired PRIVATE-HOST'))=='failed_tls_trust'
