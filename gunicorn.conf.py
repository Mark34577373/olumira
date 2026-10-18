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
