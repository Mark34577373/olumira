"""Opt-in reviewed server defaults; proxy hops/hosts remain application settings."""

# No query, referrer, user-agent, cookie, authorization or body atoms.
accesslog = "-"
access_log_format = "%(m)s %(U)s %(s)s %(L)s"
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):
    import logging
    from olumira.privacy_logging import configure_access_logging

    logging.getLogger("olumira").setLevel(logging.INFO)
    configure_access_logging()

# One small instance: maximum four web DB connections; no CPU-count multiplier.
import os
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
worker_class = 'gthread'
threads = 2
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
# Flask owns explicit proxy trust; Gunicorn must not trust arbitrary forwarded headers.
forwarded_allow_ips = ''
