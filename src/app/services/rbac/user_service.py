"""RBAC user service - 用户管理."""

from typing import cast

import log

from app.core.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.db.models.rbac import RBACUser
from app.infrastructure.security import generate_password_hash


class RBACUserService:
    """用户管理服务"""

    def __init__(self, user_repo):
        self.user_repo = user_repo

    def create_user(
        self,
        username: str,
        password: str,
        email: str | None = None,
        nickname: str | None = None,
        role_ids: list[int] | None = None,
        is_superadmin: int = 0,
    ) -> RBACUser:
        """创建用户，成功返回用户对象，失败抛出异常."""
        if self.user_repo.is_user_exists(username):
            raise ResourceAlreadyExistsError(f"用户名已存在: {username}")
        if email and email.strip() and self.user_repo.is_email_exists(email):
            raise ResourceAlreadyExistsError(f"邮箱已被使用: {email}")
        if not email or not email.strip():
            email = None
        password_hash = generate_password_hash(password)
        user = self.user_repo.create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            nickname=nickname,
            is_superadmin=is_superadmin,
        )
        if not user or isinstance(user, bool):
            user = self.user_repo.get_user_by_username(username)
        if not user:
            raise ResourceNotFoundError("用户创建失败")
        if role_ids:
            self.user_repo.assign_roles_to_user(user.ID, role_ids)
        log.info(f"[RBAC]创建用户成功: {username}")
        return user

    def update_user(self, user_id: int, **kwargs) -> None:
        """更新用户信息，失败抛出异常."""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"用户不存在: id={user_id}")
        if "email" in kwargs and kwargs["email"] != user.EMAIL:
            if self.user_repo.is_email_exists(kwargs["email"]):
                raise ResourceAlreadyExistsError(f"邮箱已被使用: {kwargs['email']}")
        success = self.user_repo.update_user(user_id, **kwargs)
        if not success:
            raise ResourceNotFoundError("更新失败")

    def delete_user(self, user_id: int) -> None:
        """删除用户，失败抛出异常."""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"用户不存在: id={user_id}")
        success = self.user_repo.delete_user(user_id)
        if not success:
            raise ResourceNotFoundError("删除失败")
        log.info(f"[RBAC]删除用户: {user.USERNAME}")

    def get_user_by_id(self, user_id: int) -> RBACUser | None:
        return cast(RBACUser | None, self.user_repo.get_user_by_id(user_id))

    def get_user_by_username(self, username: str) -> RBACUser | None:
        return cast(RBACUser | None, self.user_repo.get_user_by_username(username))

    def get_users(self, page: int = 1, page_size: int = 20) -> tuple:
        return self.user_repo.get_users(page=page, page_size=page_size)

    def assign_roles_to_user(self, user_id: int, role_ids: list[int]) -> None:
        """为用户分配角色，失败抛出异常."""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"用户不存在: id={user_id}")
        success = self.user_repo.assign_roles_to_user(user_id, role_ids)
        if not success:
            raise ResourceNotFoundError("角色分配失败")

    def get_user_roles(self, user_id: int):
        """获取用户的角色列表"""
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return []
        return self.user_repo.get_user_roles(user_id)
