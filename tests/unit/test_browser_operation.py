"""浏览器操作 trace/指标/失败截图测试。"""

import base64
from pathlib import Path
from types import SimpleNamespace

from app.domain.browser_operation import BROWSER_METRICS, BrowserOperationContext
from app.infrastructure.chrome import diagnostics


def test_operation_context_fields():
    ctx = BrowserOperationContext.create("search", "example.com")
    text = ctx.fields(keyword="x")
    assert "trace=" in text
    assert "op='search'" in text
    assert "site='example.com'" in text


def test_metrics_record_challenge_and_failure():
    BROWSER_METRICS.record_challenge("cf", solved=True)
    BROWSER_METRICS.record_failure("search")
    snap = BROWSER_METRICS.snapshot()
    assert snap["challenges"]["cf"]["total"] >= 1
    assert snap["challenges"]["cf"]["solved"] >= 1
    assert snap["failures"]["search"] >= 1


def test_capture_failure_screenshot(tmp_path, monkeypatch):
    class _Session:
        def screenshot(self, **_kwargs):
            return {"png_base64": base64.b64encode(b"png").decode()}

    monkeypatch.setattr(diagnostics, "settings", SimpleNamespace(data_path=str(tmp_path)))
    ctx = BrowserOperationContext.create("search", "example.com")
    path = diagnostics.capture_failure_screenshot(_Session(), ctx, "challenge failed")
    assert path is not None
    assert Path(path).read_bytes() == b"png"
