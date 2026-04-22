# -*- coding: utf-8 -*-
"""
RBAC 领域实体
包含用户、角色、权限、菜单等实体
"""
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class RBACUserEntity:
    """RBAC用户实体"""
    id: int
    username: str
    password_hash: str
    email: Optional[str]
    nickname: Optional[str]
    avatar: Optional[str]
    status: int
    is_superadmin: int
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACUserEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            username=orm_model.USERNAME or "",
            password_hash=orm_model.PASSWORD_HASH or "",
            email=getattr(orm_model, 'EMAIL', None),
            nickname=getattr(orm_model, 'NICKNAME', None),
            avatar=getattr(orm_model, 'AVATAR', None),
            status=getattr(orm_model, 'STATUS', 1),
            is_superadmin=getattr(orm_model, 'IS_SUPERADMIN', 0),
            last_login_at=getattr(orm_model, 'LAST_LOGIN_AT', None),
            last_login_ip=getattr(orm_model, 'LAST_LOGIN_IP', None),
            created_at=getattr(orm_model, 'CREATED_AT', None),
            updated_at=getattr(orm_model, 'UPDATED_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "status": self.status,
            "is_superadmin": self.is_superadmin,
            "last_login_at": self.last_login_at.strftime('%Y-%m-%d %H:%M:%S') if self.last_login_at else None,
            "last_login_ip": self.last_login_ip,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


@dataclass
class RBACRoleEntity:
    """RBAC角色实体"""
    id: int
    role_name: str
    role_code: str
    description: Optional[str]
    role_level: int
    status: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACRoleEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            role_name=orm_model.ROLE_NAME or "",
            role_code=orm_model.ROLE_CODE or "",
            description=getattr(orm_model, 'DESCRIPTION', None),
            role_level=getattr(orm_model, 'ROLE_LEVEL', 100),
            status=getattr(orm_model, 'STATUS', 1),
            created_at=getattr(orm_model, 'CREATED_AT', None),
            updated_at=getattr(orm_model, 'UPDATED_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role_name": self.role_name,
            "role_code": self.role_code,
            "description": self.description,
            "role_level": self.role_level,
            "status": self.status,
        }


@dataclass
class RBACPermissionEntity:
    """RBAC权限实体"""
    id: int
    permission_name: str
    permission_code: str
    description: Optional[str]
    permission_type: str
    module: Optional[str]
    status: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACPermissionEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            permission_name=orm_model.PERMISSION_NAME or "",
            permission_code=orm_model.PERMISSION_CODE or "",
            description=getattr(orm_model, 'DESCRIPTION', None),
            permission_type=getattr(orm_model, 'PERMISSION_TYPE', 'api'),
            module=getattr(orm_model, 'MODULE', None),
            status=getattr(orm_model, 'STATUS', 1),
            created_at=getattr(orm_model, 'CREATED_AT', None),
            updated_at=getattr(orm_model, 'UPDATED_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "permission_name": self.permission_name,
            "permission_code": self.permission_code,
            "description": self.description,
            "permission_type": self.permission_type,
            "module": self.module,
            "status": self.status,
        }


@dataclass
class RBACMenuEntity:
    """RBAC菜单实体"""
    id: int
    menu_name: str
    menu_code: str
    parent_id: Optional[int]
    path: Optional[str]
    icon: Optional[str]
    component: Optional[str]
    sort_order: int
    menu_level: int
    is_hidden: int
    is_external: int
    external_link: Optional[str]
    status: int
    permission_code: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACMenuEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            menu_name=orm_model.MENU_NAME or "",
            menu_code=orm_model.MENU_CODE or "",
            parent_id=getattr(orm_model, 'PARENT_ID', None),
            path=getattr(orm_model, 'PATH', None),
            icon=getattr(orm_model, 'ICON', None),
            component=getattr(orm_model, 'COMPONENT', None),
            sort_order=getattr(orm_model, 'SORT_ORDER', 0),
            menu_level=getattr(orm_model, 'MENU_LEVEL', 1),
            is_hidden=getattr(orm_model, 'IS_HIDDEN', 0),
            is_external=getattr(orm_model, 'IS_EXTERNAL', 0),
            external_link=getattr(orm_model, 'EXTERNAL_LINK', None),
            status=getattr(orm_model, 'STATUS', 1),
            permission_code=getattr(orm_model, 'PERMISSION_CODE', None),
            created_at=getattr(orm_model, 'CREATED_AT', None),
            updated_at=getattr(orm_model, 'UPDATED_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "menu_name": self.menu_name,
            "menu_code": self.menu_code,
            "parent_id": self.parent_id,
            "path": self.path,
            "icon": self.icon,
            "component": self.component,
            "sort_order": self.sort_order,
            "menu_level": self.menu_level,
            "is_hidden": self.is_hidden,
            "is_external": self.is_external,
            "external_link": self.external_link,
            "status": self.status,
            "permission_code": self.permission_code,
        }


@dataclass
class RBACUserLoginLogEntity:
    """RBAC登录日志实体"""
    id: int
    user_id: int
    username: str
    login_ip: Optional[str]
    login_location: Optional[str]
    user_agent: Optional[str]
    login_type: str
    login_status: int
    fail_reason: Optional[str]
    login_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACUserLoginLogEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            user_id=orm_model.USER_ID,
            username=orm_model.USERNAME or "",
            login_ip=getattr(orm_model, 'LOGIN_IP', None),
            login_location=getattr(orm_model, 'LOGIN_LOCATION', None),
            user_agent=getattr(orm_model, 'USER_AGENT', None),
            login_type=getattr(orm_model, 'LOGIN_TYPE', 'password'),
            login_status=getattr(orm_model, 'LOGIN_STATUS', 1),
            fail_reason=getattr(orm_model, 'FAIL_REASON', None),
            login_at=getattr(orm_model, 'LOGIN_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "login_ip": self.login_ip,
            "login_location": self.login_location,
            "login_type": self.login_type,
            "login_status": self.login_status,
            "fail_reason": self.fail_reason,
            "login_at": self.login_at.strftime('%Y-%m-%d %H:%M:%S') if self.login_at else None,
        }


@dataclass
class RBACOperationLogEntity:
    """RBAC操作日志实体"""
    id: int
    user_id: Optional[int]
    username: Optional[str]
    module: Optional[str]
    operation_type: str
    description: Optional[str]
    request_method: Optional[str]
    request_url: Optional[str]
    request_params: Optional[str]
    response_data: Optional[str]
    operation_ip: Optional[str]
    execution_time: Optional[int]
    operation_status: int
    error_msg: Optional[str]
    operated_at: Optional[datetime]

    @classmethod
    def from_orm(cls, orm_model) -> Optional["RBACOperationLogEntity"]:
        if orm_model is None:
            return None
        return cls(
            id=orm_model.ID,
            user_id=getattr(orm_model, 'USER_ID', None),
            username=getattr(orm_model, 'USERNAME', None),
            module=getattr(orm_model, 'MODULE', None),
            operation_type=orm_model.OPERATION_TYPE or "",
            description=getattr(orm_model, 'DESCRIPTION', None),
            request_method=getattr(orm_model, 'REQUEST_METHOD', None),
            request_url=getattr(orm_model, 'REQUEST_URL', None),
            request_params=getattr(orm_model, 'REQUEST_PARAMS', None),
            response_data=getattr(orm_model, 'RESPONSE_DATA', None),
            operation_ip=getattr(orm_model, 'OPERATION_IP', None),
            execution_time=getattr(orm_model, 'EXECUTION_TIME', None),
            operation_status=getattr(orm_model, 'OPERATION_STATUS', 1),
            error_msg=getattr(orm_model, 'ERROR_MSG', None),
            operated_at=getattr(orm_model, 'OPERATED_AT', None),
        )

    def __getattr__(self, name: str):
        lower_name = name.lower()
        if lower_name in {f.name for f in fields(self)}:
            return getattr(self, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "module": self.module,
            "operation_type": self.operation_type,
            "description": self.description,
            "request_method": self.request_method,
            "request_url": self.request_url,
            "operation_ip": self.operation_ip,
            "execution_time": self.execution_time,
            "operation_status": self.operation_status,
            "error_msg": self.error_msg,
            "operated_at": self.operated_at.strftime('%Y-%m-%d %H:%M:%S') if self.operated_at else None,
        }
