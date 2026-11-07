"""浏览器自动化统一任务/页面生命周期。

所有自动化调用统一使用：
- ``browser_task`` 持有持久会话（Cookie/clearance 复用）；
- ``task.page`` 为一次操作创建独占 auto_* 临时页；
- 页面退出时只关闭自己的 tab，绝不关闭用户 tab_N；
- 导航、过盾、二次刷新、Cookie 同步、点击/输入/执行 JS/截图都在这一层统一。
"""

import time
import uuid
from typing import Any

import log
from app.infrastructure.chrome.challenge import is_challenge, wait_challenge_clear
from app.infrastructure.chrome.session import BrowserSession


class BrowserPageError(RuntimeError):
    """页面导航或挑战失败。"""


class BrowserPage:
    """一次浏览器操作的独占页面（auto_* 临时标签页）。"""

    def __init__(
        self,
        task: "BrowserTask",
        url: str,
        *,
        cookie: str | None = None,
        referer: str | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        self.task = task
        self.session = task.session
        self.url = url
        self.cookie = cookie
        self.referer = referer
        self.timeout = timeout or task.navigate_timeout
        self.retries = task.challenge_retries if retries is None else retries
        self.name = f"auto_task_{uuid.uuid4().hex[:12]}"
        self._closed = False
        self._html = ""
        state = self.session.tabs_state()
        self._active_before = state.get("active")
        self.task._owned_tabs.add(self.name)

    def __enter__(self) -> "BrowserPage":
        self.load(self.url, cookie=self.cookie, referer=self.referer, timeout=self.timeout)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def load(
        self,
        url: str,
        *,
        cookie: str | None = None,
        referer: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """导航并确保脱离挑战；挑战失败时刷新重试（默认两次）。"""
        self.url = url
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                data = self.session.navigate(
                    url,
                    tab_name=self.name,
                    cookie=cookie if cookie is not None else self.cookie,
                    referer=referer,
                    timeout=timeout or self.timeout,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                log.warn(f"[BrowserPage] 导航失败 attempt={attempt + 1}: {url}: {exc}")
                continue
            html = str(data.get("html") or "")
            challenge = data.get("challenge") or {}
            if is_challenge(html) or challenge.get("solved") is False:
                html = wait_challenge_clear(
                    self.session,
                    html,
                    timeout=self.task.challenge_timeout,
                    tab_name=self.name,
                )
            if not is_challenge(html):
                self._html = html
                self.task._last_url = str(data.get("url") or url)
                return html
            last_error = "Cloudflare/挑战未通过"
            log.warn(f"[BrowserPage] 挑战未通过 attempt={attempt + 1}/{self.retries + 1}: {url}")
        raise BrowserPageError(last_error or f"页面加载失败: {url}")

    def refresh(self) -> str:
        return self.load(self.url, cookie=self.cookie, referer=self.referer)

    def html(self) -> str:
        self._html = self.session.html(self.name)
        return self._html

    def current_page(self) -> dict[str, Any]:
        return self.session.current_page(self.name)

    def click(self, selector: str) -> None:
        self._activate()
        self.session.click(selector)

    def input(self, selector: str, text: str) -> None:
        self._activate()
        self.session.input(selector, text)

    def execute(self, script: str) -> Any:
        self._activate()
        return self.session.execute(script, tab_name=self.name)

    def turnstile(self, timeout: int = 25) -> dict[str, Any]:
        self._activate()
        return self.session.turnstile(timeout=timeout)

    def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        self._activate()
        return self.session.screenshot(tab_name=self.name, full_page=full_page)

    def wait_challenge(self, timeout: int | None = None) -> str:
        self._html = wait_challenge_clear(
            self.session,
            self._html,
            timeout=timeout or self.task.challenge_timeout,
            tab_name=self.name,
        )
        return self._html

    def _activate(self) -> None:
        try:
            self.session.switch_tab(self.name)
        except Exception:
            # tab 已关闭时让调用方看到真实错误，而不是静默点击错误页面。
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.session.close_tab(self.name)
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[BrowserPage] 关闭临时标签页失败 {self.name}: {exc}")
        self.task._owned_tabs.discard(self.name)
        if self._active_before:
            try:
                names = {str(t.get("name")) for t in self.session.list_tabs() if isinstance(t, dict)}
                if self._active_before in names:
                    self.session.switch_tab(self._active_before)
            except Exception as exc:  # noqa: BLE001
                log.debug(f"[BrowserPage] 恢复活动标签页失败: {exc}")


class BrowserTask:
    """一个站点的自动化任务生命周期。"""

    def __init__(
        self,
        site_key: str,
        *,
        server_url: str,
        fingerprint: str = "stealth",
        user_agent: str | None = None,
        proxy_url: str | None = None,
        fp_profile_id: str | None = None,
        persist: bool = True,
        navigate_timeout: int = 60,
        challenge_timeout: int = 120,
        challenge_retries: int = 1,
        timeout: float = 60.0,
    ) -> None:
        self.session = BrowserSession(
            site_key,
            server_url=server_url,
            fingerprint=fingerprint,
            user_agent=user_agent,
            proxy_url=proxy_url,
            fp_profile_id=fp_profile_id,
            persist=persist,
            timeout=timeout,
        )
        self.navigate_timeout = navigate_timeout
        self.challenge_timeout = challenge_timeout
        self.challenge_retries = challenge_retries
        self._owned_tabs: set[str] = set()
        self._last_url = ""

    def __enter__(self) -> "BrowserTask":
        self.session.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        for name in list(self._owned_tabs):
            try:
                self.session.close_tab(name)
            except Exception as e:  # noqa: BLE001
                log.debug(f"[BrowserTask] 清理临时标签页失败 {name}: {e}")
        self._owned_tabs.clear()
        self.session.__exit__(*exc)

    def page(
        self,
        url: str,
        *,
        cookie: str | None = None,
        referer: str | None = None,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> BrowserPage:
        return BrowserPage(self, url, cookie=cookie, referer=referer, timeout=timeout, retries=retries)

    def wait(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


def browser_task(site_key: str, **kwargs: Any) -> BrowserTask:
    """创建统一浏览器任务。"""
    return BrowserTask(site_key, **kwargs)
