# -*- coding: utf-8 -*-
"""
API Key Service
API Key 业务逻辑层
"""
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.db.repositories.apikey_repo_adapter import APIKeyRepositoryAdapter, APIKeyLogRepositoryAdapter
from app.utils import ExceptionUtils
import log


class APIKeyService:
    """API Key 管理服务"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._key_repo = APIKeyRepositoryAdapter()
        self._log_repo = APIKeyLogRepositoryAdapter()
        self._initialized = True

    @staticmethod
    def _generate_raw_key() -> str:
        """生成原始 API Key"""
        return "nk_" + secrets.token_urlsafe(32)

    @staticmethod
    def _hash_key(key: str) -> str:
        """对 API Key 进行 SHA256 哈希"""
        return hashlib.sha256(key.encode()).hexdigest()

    def create_key(self, name: str, expires_days: Optional[int] = None,
                   description: str = "", created_by: Optional[int] = None) -> Dict[str, Any]:
        """
        创建新的 API Key
        """
        try:
            raw_key = self._generate_raw_key()
            key_hash = self._hash_key(raw_key)
            key_prefix = raw_key[:12] + "..."

            expires_at = None
            if expires_days is not None and expires_days > 0:
                expires_at = datetime.now() + timedelta(days=expires_days)

            api_key = self._key_repo.create_key(
                name=name,
                key_value=key_hash,
                key_prefix=key_prefix,
                expires_at=expires_at,
                created_by=created_by,
                description=description,
            )

            log.info(f"【APIKey】创建成功: {name} (ID={api_key.id})")

            return {
                "id": api_key.id,
                "name": api_key.name,
                "key": raw_key,
                "prefix": key_prefix,
                "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
                "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
                "status": api_key.status,
            }
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            raise

    def list_keys(self, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """获取 API Key 列表"""
        try:
            items, total = self._key_repo.list_keys(page, page_size)
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [item.to_dict() for item in items],
            }
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"total": 0, "page": page, "page_size": page_size, "items": []}

    def update_key(self, key_id: int, name: Optional[str] = None,
                   status: Optional[int] = None,
                   description: Optional[str] = None) -> bool:
        """更新 API Key"""
        try:
            kwargs = {}
            if name is not None:
                kwargs["name"] = name
            if status is not None:
                kwargs["status"] = status
            if description is not None:
                kwargs["description"] = description
            return self._key_repo.update_key(key_id, **kwargs)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def delete_key(self, key_id: int) -> bool:
        """删除 API Key"""
        try:
            return self._key_repo.delete_key(key_id)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def validate_key(self, raw_key: str) -> Optional[Any]:
        """验证 API Key 是否有效"""
        try:
            key_hash = self._hash_key(raw_key)
            key = self._key_repo.get_by_key_and_status(key_hash, status=1)
            if not key or key.is_expired():
                return None
            return key
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return None

    def record_usage(self, api_key_id: int, request_id: Optional[str] = None,
                     request_name: str = "", source_ip: str = "",
                     user_agent: str = "", request_path: str = "",
                     request_method: str = "", status: int = 1,
                     response_code: Optional[int] = None,
                     error_message: str = "",
                     response_time_ms: Optional[int] = None) -> bool:
        """记录 API Key 使用日志"""
        try:
            if request_id is None:
                request_id = str(uuid.uuid4())

            self._log_repo.create_log(
                api_key_id=api_key_id,
                request_id=request_id,
                request_name=request_name,
                source_ip=source_ip,
                user_agent=user_agent,
                request_path=request_path,
                request_method=request_method,
                status=status,
                response_code=response_code,
                error_message=error_message,
                response_time_ms=response_time_ms,
            )
            self._key_repo.increment_use_count(api_key_id)
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False

    def list_logs(self, api_key_id: Optional[int] = None,
                  page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """获取 API Key 使用记录"""
        try:
            items, total = self._log_repo.list_logs(api_key_id, page, page_size)
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [item.to_dict() for item in items],
            }
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"total": 0, "page": page, "page_size": page_size, "items": []}

    def get_stats(self) -> Dict[str, Any]:
        """获取 API Key 统计信息"""
        try:
            return self._key_repo.get_stats()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {
                "total_keys": 0,
                "active_keys": 0,
                "total_requests": 0,
                "today_requests": 0,
            }
