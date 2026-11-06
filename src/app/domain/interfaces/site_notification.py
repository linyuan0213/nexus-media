"""站点通知端口.

站点层只依赖通知能力协议，不直接依赖 message 实现或 WebMessageStore。
"""

from __future__ import annotations

from typing import Protocol


class ISiteNotifier(Protocol):
    def send_site_message(self, title: str | None = None, text: str | None = None) -> None: ...

    def send_user_statistics_message(self, msgs: list) -> None: ...

    def recent_web_messages(self, *, user_id: str = "", limit: int = 20) -> list[dict]: ...
