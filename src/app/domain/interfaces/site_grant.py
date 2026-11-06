"""站点授权端口.

索引器等下层组件只依赖该协议，不直接依赖 services.site_grant_service。
"""

from __future__ import annotations

from typing import Any, Protocol


class ISiteGrantService(Protocol):
    def get_visible_sites_by_id(self, user_id: int) -> Any: ...

    def is_site_allowed(self, visible: Any, site_name: str, source: str, *, usage: str) -> bool: ...
