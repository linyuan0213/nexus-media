"""站点授权 Repository（L3 资源访问控制）.

RBAC_ROLE_SITES（角色级）+ RBAC_USER_SITES（用户级例外）两张表，
PERMISSIONS 为 JSON 列表（search/rss），有效授权为纯并集。
"""

import json

from app.db.models import RBACRoleSite, RBACUserSite
from app.db.repositories.base_repository import BaseRepository

VALID_SITE_PERMISSIONS = {"search", "rss"}


def normalize_permissions(raw) -> list[str]:
    """解析并过滤 PERMISSIONS JSON，非法项丢弃，空则回退 search."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = []
    if not isinstance(raw, list):
        raw = []
    perms = sorted({str(p) for p in raw if str(p) in VALID_SITE_PERMISSIONS})
    return perms or ["search"]


class SiteGrantRepository(BaseRepository):
    """站点授权仓储"""

    def get_role_grants(self, role_id: int) -> list[RBACRoleSite]:
        with self.session() as db:
            return db.query(RBACRoleSite).filter(RBACRoleSite.ROLE_ID == role_id).all()

    def get_user_grants(self, user_id: int) -> list[RBACUserSite]:
        with self.session() as db:
            return db.query(RBACUserSite).filter(RBACUserSite.USER_ID == user_id).all()

    def get_grants_by_roles(self, role_ids: list[int]) -> list[RBACRoleSite]:
        """批量查询多个角色的站点授权"""
        if not role_ids:
            return []
        with self.session() as db:
            return db.query(RBACRoleSite).filter(RBACRoleSite.ROLE_ID.in_(role_ids)).all()

    def set_role_grants(self, role_id: int, grants: list[dict], granted_by: int | None = None) -> None:
        """全量覆盖角色站点授权. grants: [{"site_name": ..., "permissions": [...]}]"""
        with self.session() as db:
            db.query(RBACRoleSite).filter(RBACRoleSite.ROLE_ID == role_id).delete()
            for grant in grants:
                site_name = str(grant.get("site_name") or "").strip()
                if not site_name:
                    continue
                db.add(
                    RBACRoleSite(
                        ROLE_ID=role_id,
                        SITE_NAME=site_name,
                        PERMISSIONS=json.dumps(normalize_permissions(grant.get("permissions"))),
                        GRANTED_BY=granted_by,
                    )
                )

    def set_user_grants(self, user_id: int, grants: list[dict], granted_by: int | None = None) -> None:
        """全量覆盖用户站点授权. grants: [{"site_name": ..., "permissions": [...]}]"""
        with self.session() as db:
            db.query(RBACUserSite).filter(RBACUserSite.USER_ID == user_id).delete()
            for grant in grants:
                site_name = str(grant.get("site_name") or "").strip()
                if not site_name:
                    continue
                db.add(
                    RBACUserSite(
                        USER_ID=user_id,
                        SITE_NAME=site_name,
                        PERMISSIONS=json.dumps(normalize_permissions(grant.get("permissions"))),
                        GRANTED_BY=granted_by,
                    )
                )

    def get_user_effective_grants(self, user_id: int, role_ids: list[int]) -> dict[str, set[str]]:
        """用户有效站点授权 = 角色级 ∪ 用户级，返回 {site_name: {permissions}}"""
        effective: dict[str, set[str]] = {}
        for row in self.get_grants_by_roles(role_ids):
            effective.setdefault(row.SITE_NAME, set()).update(normalize_permissions(row.PERMISSIONS))
        for row in self.get_user_grants(user_id):
            effective.setdefault(row.SITE_NAME, set()).update(normalize_permissions(row.PERMISSIONS))
        return effective
