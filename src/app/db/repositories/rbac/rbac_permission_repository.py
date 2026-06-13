"""
RBAC Repository
基于角色的访问控制(RBAC)数据访问层
处理用户、角色、权限、菜单的数据库操作
"""

from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.models.rbac import (
    RBACPermission,
)
from app.db.repositories.base_repository import BaseRepository


class RBACPermissionRepository(BaseRepository):
    """
    RBAC权限管理仓储
    """

    def _get_permission_by_id(self, db: Session, permission_id: int) -> RBACPermission | None:
        """在同一 session 内根据ID获取权限。"""
        return db.query(RBACPermission).filter(RBACPermission.ID == permission_id).first()

    def get_permission_by_id(self, permission_id: int) -> RBACPermission | None:
        """
        根据ID获取权限
        """
        with self.session() as db:
            return self._get_permission_by_id(db, permission_id)

    def get_permission_by_code(self, permission_code: str) -> RBACPermission | None:
        """
        根据权限代码获取权限
        """
        with self.session() as db:
            return (
                db.query(RBACPermission)
                .filter(RBACPermission.PERMISSION_CODE == permission_code, RBACPermission.STATUS == 1)
                .first()
            )

    def get_all_permissions(
        self, module: str | None = None, permission_type: str | None = None
    ) -> list[RBACPermission]:
        """
        获取所有权限

        Args:
            module: 模块筛选
            permission_type: 权限类型筛选

        Returns:
            权限列表
        """
        with self.session() as db:
            query = db.query(RBACPermission).filter(RBACPermission.STATUS == 1)

            if module:
                query = query.filter(RBACPermission.MODULE == module)
            if permission_type:
                query = query.filter(RBACPermission.PERMISSION_TYPE == permission_type)

            return query.order_by(RBACPermission.MODULE, RBACPermission.PERMISSION_CODE).all()

    def get_permissions_by_codes(self, codes: list[str]) -> list[RBACPermission]:
        """
        根据权限代码列表获取权限
        """
        with self.session() as db:
            return (
                db.query(RBACPermission)
                .filter(and_(RBACPermission.PERMISSION_CODE.in_(codes), RBACPermission.STATUS == 1))
                .all()
            )

    def create_permission(
        self,
        permission_name: str,
        permission_code: str,
        permission_type: str = "api",
        module: str | None = None,
        description: str | None = None,
    ) -> RBACPermission:
        """
        创建权限
        """
        with self.session() as db:
            permission = RBACPermission(
                PERMISSION_NAME=permission_name,
                PERMISSION_CODE=permission_code,
                PERMISSION_TYPE=permission_type,
                MODULE=module,
                DESCRIPTION=description,
                STATUS=1,
            )
            db.add(permission)
            db.commit()
            return permission

    def update_permission(self, permission_id: int, **kwargs) -> bool:
        """
        更新权限信息
        """
        with self.session() as db:
            permission = self._get_permission_by_id(db, permission_id)
            if not permission:
                return False

            allowed_fields = ["PERMISSION_NAME", "DESCRIPTION", "STATUS", "MODULE"]
            for key, value in kwargs.items():
                if key.upper() in allowed_fields:
                    setattr(permission, key.upper(), value)

            permission.UPDATED_AT = datetime.now()  # type: ignore[assignment]
            db.commit()
            return True

    def delete_permission(self, permission_id: int) -> bool:
        """
        删除权限
        """
        with self.session() as db:
            result = db.query(RBACPermission).filter(RBACPermission.ID == permission_id).delete()
            db.commit()
            return result > 0
