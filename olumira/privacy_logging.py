"""Keep journal search terms and query values out of local HTTP access logs."""

import logging
import re


class AccessPathFilter(logging.Filter):
    def filter(self, record):
        def redact(value):
            if not isinstance(value, str):
                return value
            return re.sub(
                r"([A-Z]+ )([^ ]+)( HTTP/\d(?:\.\d)?)",
                lambda match: match[1] + match[2].split("?", 1)[0] + match[3],
                value,
            )

        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        record.msg = redact(record.msg)
        return True


def configure_access_logging():
    logger = logging.getLogger("werkzeug")
    if not any(isinstance(item, AccessPathFilter) for item in logger.filters):
        logger.addFilter(AccessPathFilter())
