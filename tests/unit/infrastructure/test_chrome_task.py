"""BrowserTask/BrowserPage 生命周期测试."""

from types import SimpleNamespace
from typing import cast

from app.infrastructure.chrome.task import BrowserPage, BrowserTask


class _FakeSession:
    def __init__(self):
        self.active = "tab_1"
        self.calls = []
        self.closed = []

    def tabs_state(self):
        return {"active": self.active, "tabs": [{"name": "tab_1", "url": "https://example.com"}]}

    def list_tabs(self):
        return self.tabs_state()["tabs"]

    def navigate(self, url, **kwargs):
        self.calls.append(("navigate", url, kwargs["tab_name"]))
        self.active = kwargs["tab_name"]
        return {"url": url, "html": "<html><title>ok</title></html>", "challenge": {"solved": True}}

    def html(self, tab_name=None):
        return "<html><title>ok</title></html>"

    def switch_tab(self, name):
        self.calls.append(("switch", name))
        self.active = name

    def click(self, selector):
        self.calls.append(("click", selector))

    def close_tab(self, name):
        self.closed.append(name)


def _task(session):
    return cast(
        BrowserTask,
        SimpleNamespace(
            session=session,
            navigate_timeout=60,
            challenge_timeout=120,
            challenge_retries=1,
            _owned_tabs=set(),
            _last_url="",
        ),
    )


def test_page_owns_tab_click_and_cleanup():
    session = _FakeSession()
    task = _task(session)
    page = BrowserPage(task, "https://example.com/page")

    with page:
        page.click("button.submit")
        assert page.html() == "<html><title>ok</title></html>"
        assert page.name.startswith("auto_task_")
        assert ("click", "button.submit") in session.calls

    assert session.closed == [page.name]
    assert session.active == "tab_1"


def test_page_close_is_idempotent():
    session = _FakeSession()
    page = BrowserPage(_task(session), "https://example.com/page")
    with page:
        pass
    page.close()
    assert session.closed == [page.name]
