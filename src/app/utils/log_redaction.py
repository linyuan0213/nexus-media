"""日志脱敏：避免 RSS passkey / API Key 等敏感查询参数落盘."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_KEYS = (
    "passkey",
    "torrent_pass",
    "authkey",
    "apikey",
    "api_key",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "signature",
    "sig",
    "pan_auth",
    "auth",
)
_KEY_PATTERN = "|".join(re.escape(key) for key in _SECRET_KEYS)
_QUERY_SECRET_RE = re.compile(rf"(?i)(?P<key>(?:{_KEY_PATTERN}))=(?P<value>[^&#\s]+)")


def redact_url(url: str | None) -> str:
    """替换 URL 查询参数中的敏感值，保留参数名便于排查."""
    text = str(url or "")
    if not text:
        return text
    try:
        parts = urlsplit(text)
        if not parts.query:
            return text
        query = [
            (key, "***" if key.lower() in _SECRET_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        query_text = urlencode(query, doseq=True, safe="*")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query_text, parts.fragment))
    except ValueError:
        return _QUERY_SECRET_RE.sub(lambda match: f"{match.group('key')}=***", text)


def redact_text(value: object) -> str:
    """脱敏任意日志文本中的敏感查询参数（包括异常消息中的完整 URL）."""
    text = str(value or "")
    return _QUERY_SECRET_RE.sub(lambda match: f"{match.group('key')}=***", text)
