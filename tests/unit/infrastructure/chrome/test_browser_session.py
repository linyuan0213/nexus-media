"""BrowserSession 上下文管理测试：__enter__ 失败必须归还浏览器并发名额。"""

from unittest.mock import MagicMock

import pytest

from app.infrastructure.chrome import session as session_mod
from app.infrastructure.chrome.session import BrowserSession


def test_enter_releases_slot_when_ensure_session_fails(monkeypatch):
    slot = MagicMock()
    monkeypatch.setattr(session_mod, "browser_slot", lambda: slot)

    session = BrowserSession.__new__(BrowserSession)
    session._slot = None
    monkeypatch.setattr(session, "_ensure_session", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        session.__enter__()

    slot.__enter__.assert_called_once()
    slot.__exit__.assert_called_once()
    assert session._slot is None


def test_persistent_session_keeps_active_tab_without_deleting_session():
    session = BrowserSession.__new__(BrowserSession)
    session._persist = True
    session._sid = "sid"
    session._client = MagicMock()
    session.close_tabs = MagicMock()
    session.close_inactive_tabs = MagicMock()

    session.close()

    # 持久会话保留活动标签页，只清理历史标签，否则下一次 navigate 会 500。
    session.close_tabs.assert_not_called()
    session.close_inactive_tabs.assert_called_once()
    session._client.delete.assert_not_called()
    session._client.close.assert_called_once()
