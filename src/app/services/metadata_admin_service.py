"""元数据管理服务：仅承载身份写操作，不参与业务读取。"""

from __future__ import annotations

from typing import Any

from app.services.metadata_service import MetadataService


class MetadataAdminService:
    """身份合并、链接审核与覆盖写库入口。"""

    def __init__(self, service: MetadataService) -> None:
        self._service = service

    def merge_identity(self, source_id: str, target_id: str) -> bool:
        return bool(self._service.merge_identity(source_id, target_id))

    def review_link(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        approve: bool,
        confidence: float = 1.0,
        scope: str = "default",
    ) -> dict[str, Any] | None:
        return self._service.review_link(
            identity_id,
            provider=provider,
            external_id=external_id,
            approve=approve,
            confidence=confidence,
            scope=scope,
        )

    def set_override(
        self,
        identity_id: str,
        *,
        field_name: str,
        value: str,
        user_id: int | None = None,
        locked: bool = True,
    ) -> dict[str, Any]:
        return self._service.set_override(
            identity_id,
            field_name=field_name,
            value=value,
            user_id=user_id,
            locked=locked,
        )

    def metrics(self) -> dict[str, Any]:
        return self._service.metrics()

    def bump_detail_cache_version(self) -> int:
        return int(self._service.bump_detail_cache_version())
