"""日志脱敏测试."""

from app.utils.log_redaction import redact_text, redact_url


def test_redact_url_masks_rss_passkey():
    value = redact_url("https://tracker.example/rss?rows=50&passkey=secret-value&icat=1")
    assert "passkey=***" in value
    assert "secret-value" not in value
    assert "rows=50" in value


def test_redact_text_masks_exception_url():
    value = redact_text("HTTP error for https://tracker.example/rss?authkey=abc&torrent_pass=xyz")
    assert "authkey=***" in value
    assert "torrent_pass=***" in value
    assert "abc" not in value
    assert "xyz" not in value
