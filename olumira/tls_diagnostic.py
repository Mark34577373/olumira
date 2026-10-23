"""Opt-in TLS metadata only. Never emit paths, endpoint names or certificate data."""
import os
import ssl
from pathlib import Path

from cryptography import x509


def bundle_status(filename):
    try:
        path = Path(filename).expanduser()
        if not path.is_file():
            return dict(bundle_status='missing', certificate_count=0)
        if path.stat().st_size > 8 * 1024 * 1024:
            return dict(bundle_status='too_large', certificate_count=0)
        certificates = x509.load_pem_x509_certificates(path.read_bytes())
        return dict(bundle_status='parsed' if certificates else 'empty', certificate_count=len(certificates))
    except PermissionError:
        return dict(bundle_status='unreadable', certificate_count=0)
    except (OSError, ValueError):
        return dict(bundle_status='invalid_or_unreadable', certificate_count=0)


def report(app, engine, emit):
    if engine.dialect.name != 'postgresql':
        return
    import psycopg
    from psycopg import pq

    emit(app, 'tls_runtime', 'checked', psycopg_version=psycopg.__version__,
         libpq_version=pq.version(), implementation=pq.__impl__,
         system_roots_supported=pq.version() >= 160000)
    _, parameters = engine.dialect.create_connect_args(engine.url)
    overrides = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('connect_args', {})
    parameters.update(overrides)
    mode = parameters.get('sslmode', os.getenv('PGSSLMODE', 'prefer'))
    root = parameters.get('sslrootcert', os.getenv('PGSSLROOTCERT', ''))
    source = 'system' if root == 'system' else 'file' if isinstance(root, str) and root else 'libpq_default'
    duplicate = any(isinstance(engine.url.query.get(key), tuple) for key in ('sslmode', 'sslrootcert'))
    emit(app, 'tls_parameters', 'checked',
         sslmode=mode if mode in ('disable','allow','prefer','require','verify-ca','verify-full') else 'unrecognized',
         hostname_verification_required=mode == 'verify-full', root_source=source,
         sqlalchemy_tls_override=any(key in overrides for key in ('sslmode','sslrootcert')),
         duplicate_tls_parameters=duplicate,
         pgsslrootcert_configured=bool(os.getenv('PGSSLROOTCERT')),
         ssl_cert_file_configured=bool(os.getenv('SSL_CERT_FILE')),
         ssl_cert_dir_configured=bool(os.getenv('SSL_CERT_DIR')),
         pgservice_configured=bool(os.getenv('PGSERVICE') or parameters.get('service')),
         host_override=bool(engine.url.query.get('host') or parameters.get('hostaddr') or os.getenv('PGHOSTADDR')))
    if source != 'system':
        emit(app, 'tls_root_bundle', 'checked', **bundle_status(root if source == 'file' else '~/.postgresql/root.crt'))
    else:
        # Python's SSL implementation can differ from binary psycopg's OpenSSL.
        # This is a filesystem/parse check, NOT proof of libpq's trust decisions.
        for label, path in (
            ('linux_system_bundle', '/etc/ssl/certs/ca-certificates.crt'),
            ('configured_ssl_cert_file', os.getenv('SSL_CERT_FILE')),
        ):
            if path:
                emit(app, label, 'checked', **bundle_status(path))
        try:
            count = len(ssl.create_default_context().get_ca_certs())
            emit(app, 'python_trust_hint', 'loaded', certificate_count=count, authoritative_for_libpq=False)
        except (OSError, ValueError, ssl.SSLError):
            emit(app, 'python_trust_hint', 'unavailable', authoritative_for_libpq=False)


def failure_detail(error):
    """Known TLS error phrases mapped to fixed hints, never raw certificate data."""
    message=str(getattr(error,'orig',None) or error).lower()
    if 'root certificate file' in message:
        if 'does not exist' in message or 'no such file' in message:
            return 'root_file_missing'
        if 'permission denied' in message:
            return 'root_file_unreadable'
        return 'root_file_error'
    for phrase,detail in (
        ('certificate has expired','certificate_expired'),
        ('certificate is not yet valid','certificate_not_yet_valid'),
        ('self-signed certificate','self_signed_untrusted'),
        ('unable to get local issuer certificate','issuer_chain_untrusted'),
    ):
        if phrase in message:return detail
    return 'verification_failed_unspecified'
