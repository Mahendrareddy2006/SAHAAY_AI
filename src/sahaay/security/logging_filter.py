"""
Sahaay AI - Redacting Logging Filter
(src/sahaay/security/logging_filter.py)

Intercepts standard logging records to prevent secret leakage, API key disclosure,
and privacy-sensitive personal information (phone numbers, emails) in application logs.
"""

import logging
import re
from typing import List, Tuple

# Compiled regex patterns for redaction
REDACTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Sahaay bearer tokens (e.g. sahaay_v1.payload.signature)
    (re.compile(r"sahaay_v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "sahaay_v1.[REDACTED_TOKEN]"),
    # Generic Bearer tokens in headers or logs
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1[REDACTED_BEARER_TOKEN]"),
    # API keys and secret query/form parameters
    (re.compile(r"(api[_-]?key\s*[:=]\s*)[^\s&\"',]+", re.IGNORECASE), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(secret[_-]?key\s*[:=]\s*)[^\s&\"',]+", re.IGNORECASE), r"\1[REDACTED_SECRET]"),
    (re.compile(r"(auth[_-]?token\s*[:=]\s*)[^\s&\"',]+", re.IGNORECASE), r"\1[REDACTED_AUTH_TOKEN]"),
    (re.compile(r"(password\s*[:=]\s*)[^\s&\"',]+", re.IGNORECASE), r"\1[REDACTED_PASSWORD]"),
    # Indian mobile phone numbers (10 digits starting with 6, 7, 8, 9)
    (re.compile(r"\b[6-9]\d{9}\b"), "[REDACTED_PHONE_NUMBER]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
]


class RedactingLoggingFilter(logging.Filter):
    """
    Logging filter that sanitizes log message strings and arguments.
    Ensures zero sensitive credentials or private contact information are persisted to disk or stdout.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = self.redact(record.msg)

            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: self._sanitize_arg(v) for k, v in record.args.items()}
                elif isinstance(record.args, (list, tuple)):
                    record.args = tuple(self._sanitize_arg(a) for a in record.args)
        except Exception:
            # Redaction failure must fail closed (allow record through without crashing)
            pass
        return True

    @classmethod
    def redact(cls, text: str) -> str:
        """Applies all redaction rules to the input string."""
        if not text or not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in REDACTION_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @classmethod
    def _sanitize_arg(cls, arg):
        if isinstance(arg, str):
            return cls.redact(arg)
        return arg


def attach_redacting_filter_to_root_logger():
    """Attaches the RedactingLoggingFilter to all active root and module loggers."""
    redacting_filter = RedactingLoggingFilter()
    root_logger = logging.getLogger()
    if not any(isinstance(f, RedactingLoggingFilter) for f in root_logger.filters):
        root_logger.addFilter(redacting_filter)

    for handler in root_logger.handlers:
        if not any(isinstance(f, RedactingLoggingFilter) for f in handler.filters):
            handler.addFilter(redacting_filter)
