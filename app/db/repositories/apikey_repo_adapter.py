# -*- coding: utf-8 -*-
"""
API Key 领域 Repository 适配器
将底层 APIKeyRepository 适配为领域接口
"""
from typing import Any, Dict, List, Optional, Tuple

from app.domain.entities.apikey import APIKeyEntity, APIKeyLogEntity
from app.domain.interfaces.apikey_repo import IAPIKeyRepository, IAPIKeyLogRepository
from app.db.repositories.apikey_repository import APIKeyRepository, APIKeyLogRepository


class APIKeyRepositoryAdapter(IAPIKeyRepository):
    """API Key 仓储适配器"""

    def __init__(self, repo: Optional[APIKeyRepository] = None):
        self._repo = repo or APIKeyRepository()

    def get_by_id(self, key_id: int) -> Optional[APIKeyEntity]:
        row = self._repo.get_by_id(key_id)
        return APIKeyEntity.from_orm(row)

    def get_by_key_value(self, key_value: str) -> Optional[APIKeyEntity]:
        row = self._repo.get_by_key_value(key_value)
        return APIKeyEntity.from_orm(row)

    def get_by_key_and_status(self, key_value: str, status: int = 1) -> Optional[APIKeyEntity]:
        row = self._repo.get_by_key_and_status(key_value, status)
        return APIKeyEntity.from_orm(row)

    def get_by_name(self, name: str, status: Optional[int] = None) -> Optional[APIKeyEntity]:
        row = self._repo.get_by_name(name, status)
        return APIKeyEntity.from_orm(row)

    def list_keys(self, page: int = 1, page_size: int = 50) -> Tuple[List[APIKeyEntity], int]:
        rows, total = self._repo.list_keys(page, page_size)
        return [e for e in [APIKeyEntity.from_orm(r) for r in rows] if e is not None], total

    def create_key(self, name: str, key_value: str, key_prefix: str,
                   status: int = 1, expires_at: Optional[Any] = None,
                   created_by: Optional[int] = None,
                   description: str = "",
                   raw_key: Optional[str] = None) -> APIKeyEntity:
        row = self._repo.create_key(name, key_value, key_prefix, status,
                                    expires_at, created_by, description, raw_key)
        return APIKeyEntity.from_orm(row)

    def update_key(self, key_id: int, **kwargs) -> bool:
        return self._repo.update_key(key_id, **kwargs)

    def delete_key(self, key_id: int) -> bool:
        return self._repo.delete_key(key_id)

    def increment_use_count(self, key_id: int) -> bool:
        return self._repo.increment_use_count(key_id)

    def get_stats(self) -> Dict[str, int]:
        return self._repo.get_stats()


class APIKeyLogRepositoryAdapter(IAPIKeyLogRepository):
    """API Key 日志仓储适配器"""

    def __init__(self, repo: Optional[APIKeyLogRepository] = None):
        self._repo = repo or APIKeyLogRepository()

    def create_log(self, api_key_id: int, request_id: str,
                   request_name: str = "", source_ip: str = "",
                   user_agent: str = "", request_path: str = "",
                   request_method: str = "", status: int = 1,
                   response_code: Optional[int] = None,
                   error_message: str = "",
                   response_time_ms: Optional[int] = None) -> APIKeyLogEntity:
        row = self._repo.create_log(api_key_id, request_id, request_name,
                                    source_ip, user_agent, request_path,
                                    request_method, status, response_code,
                                    error_message, response_time_ms)
        return APIKeyLogEntity.from_orm(row)

    def list_logs(self, api_key_id: Optional[int] = None,
                  page: int = 1, page_size: int = 50) -> Tuple[List[APIKeyLogEntity], int]:
        rows, total = self._repo.list_logs(api_key_id, page, page_size)
        return [e for e in [APIKeyLogEntity.from_orm(r) for r in rows] if e is not None], total

    def get_log_by_request_id(self, request_id: str) -> Optional[APIKeyLogEntity]:
        row = self._repo.get_log_by_request_id(request_id)
        return APIKeyLogEntity.from_orm(row)

    def delete_logs_by_key_id(self, api_key_id: int) -> int:
        return self._repo.delete_logs_by_key_id(api_key_id)
