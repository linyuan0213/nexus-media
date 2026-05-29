"""
API Key 领域 Repository 接口
"""

from typing import Any, Protocol

from app.domain.entities.apikey import APIKeyEntity, APIKeyLogEntity


class IAPIKeyRepository(Protocol):
    """API Key 仓储接口"""

    def get_by_id(self, key_id: int) -> APIKeyEntity | None: ...
    def get_by_key_value(self, key_value: str) -> APIKeyEntity | None: ...
    def get_by_key_and_status(self, key_value: str, status: int = 1) -> APIKeyEntity | None: ...
    def list_keys(self, page: int = 1, page_size: int = 50) -> tuple[list[APIKeyEntity], int]: ...
    def create_key(
        self,
        name: str,
        key_value: str,
        key_prefix: str,
        status: int = 1,
        expires_at: Any | None = None,
        created_by: int | None = None,
        description: str = "",
    ) -> APIKeyEntity: ...
    def update_key(self, key_id: int, **kwargs) -> bool: ...
    def delete_key(self, key_id: int) -> bool: ...
    def increment_use_count(self, key_id: int) -> bool: ...
    def get_stats(self) -> dict[str, int]: ...


class IAPIKeyLogRepository(Protocol):
    """API Key 日志仓储接口"""

    def create_log(
        self,
        api_key_id: int,
        request_id: str,
        request_name: str = "",
        source_ip: str = "",
        user_agent: str = "",
        request_path: str = "",
        request_method: str = "",
        status: int = 1,
        response_code: int | None = None,
        error_message: str = "",
        response_time_ms: int | None = None,
    ) -> APIKeyLogEntity: ...
    def list_logs(
        self, api_key_id: int | None = None, page: int = 1, page_size: int = 50
    ) -> tuple[list[APIKeyLogEntity], int]: ...
    def get_log_by_request_id(self, request_id: str) -> APIKeyLogEntity | None: ...
    def delete_logs_by_key_id(self, api_key_id: int) -> int: ...
