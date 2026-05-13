# -*- coding: utf-8 -*-
"""
API Key 领域实体
"""
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class APIKeyEntity:
    """API Key 实体"""
    id: int
    name: str
    key_value: str
    key_prefix: str
    status: int
    expires_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    created_by: Optional[int]
    use_count: int
    last_used_at: Optional[datetime]
    description: Optional[str]
    raw_key: Optional[str]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["APIKeyEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=getattr(orm_model, 'ID', 0),
            name=getattr(orm_model, 'NAME', ''),
            key_value=getattr(orm_model, 'KEY_VALUE', ''),
            key_prefix=getattr(orm_model, 'KEY_PREFIX', ''),
            status=getattr(orm_model, 'STATUS', 1),
            expires_at=getattr(orm_model, 'EXPIRES_AT', None),
            created_at=getattr(orm_model, 'CREATED_AT', None),
            updated_at=getattr(orm_model, 'UPDATED_AT', None),
            created_by=getattr(orm_model, 'CREATED_BY', None),
            use_count=getattr(orm_model, 'USE_COUNT', 0),
            last_used_at=getattr(orm_model, 'LAST_USED_AT', None),
            description=getattr(orm_model, 'DESCRIPTION', None),
            raw_key=getattr(orm_model, 'RAW_KEY', None),
        )

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_active(self) -> bool:
        return self.status == 1 and not self.is_expired()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "description": self.description,
            "is_expired": self.is_expired(),
            "is_active": self.is_active(),
        }


@dataclass
class APIKeyLogEntity:
    """API Key 使用记录实体"""
    id: int
    api_key_id: int
    request_id: str
    request_name: Optional[str]
    source_ip: Optional[str]
    user_agent: Optional[str]
    request_path: Optional[str]
    request_method: Optional[str]
    status: int
    response_code: Optional[int]
    error_message: Optional[str]
    request_at: Optional[datetime]
    response_time_ms: Optional[int]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["APIKeyLogEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=getattr(orm_model, 'ID', 0),
            api_key_id=getattr(orm_model, 'API_KEY_ID', 0),
            request_id=getattr(orm_model, 'REQUEST_ID', ''),
            request_name=getattr(orm_model, 'REQUEST_NAME', None),
            source_ip=getattr(orm_model, 'SOURCE_IP', None),
            user_agent=getattr(orm_model, 'USER_AGENT', None),
            request_path=getattr(orm_model, 'REQUEST_PATH', None),
            request_method=getattr(orm_model, 'REQUEST_METHOD', None),
            status=getattr(orm_model, 'STATUS', 1),
            response_code=getattr(orm_model, 'RESPONSE_CODE', None),
            error_message=getattr(orm_model, 'ERROR_MESSAGE', None),
            request_at=getattr(orm_model, 'REQUEST_AT', None),
            response_time_ms=getattr(orm_model, 'RESPONSE_TIME_MS', None),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "api_key_id": self.api_key_id,
            "request_id": self.request_id,
            "request_name": self.request_name,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "request_path": self.request_path,
            "request_method": self.request_method,
            "status": self.status,
            "response_code": self.response_code,
            "error_message": self.error_message,
            "request_at": self.request_at.isoformat() if self.request_at else None,
            "response_time_ms": self.response_time_ms,
        }
