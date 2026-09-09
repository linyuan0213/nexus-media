"""站点授权服务（L3 资源访问控制）.

可见性规则（ADR-021 4.2）：
- superadmin → 全部站点（返回 None 表示不过滤）
- 全局策略 open（默认）→ 不过滤（兼容单用户/现有行为）
- 全局策略 closed → 白名单 = 角色级授权 ∪ 用户级授权

授权键：builtin 站点用站点名；第三方索引器用 `jackett:<站点名>` / `prowlarr:<站点名>`
或 `jackett:*` / `prowlarr:*` 整体授权。
"""

from app.db.repositories.site_grant_repository import SiteGrantRepository, normalize_permissions
from app.domain.enums import SystemConfigKey
from app.infrastructure.cache_system import RBACSnapshotCache
from app.schemas.auth import SUPERADMIN_ROLE_CODE, UserContext

# 授权表允许的用途粒度
SITE_PERMISSION_SEARCH = "search"
SITE_PERMISSION_RSS = "rss"

_SNAPSHOT_KEY = "site_grants:{user_id}"


class SiteGrantService:
    """站点授权服务"""

    def __init__(self, grant_repo: SiteGrantRepository, rbac_service, system_config):
        self._grant_repo = grant_repo
        self._rbac_service = rbac_service
        self._system_config = system_config

    # ---------- 查询 ----------

    def get_visible_sites(self, user: UserContext) -> dict[str, set[str]] | None:
        """用户可见站点及用途粒度.

        Returns:
            None: 不过滤（superadmin 或 open 策略）
            dict: {授权键: {search/rss}}，closed 策略下的白名单
        """
        if user.is_superadmin:
            return None
        return self._visible_for_user(user.user_id)

    def get_visible_sites_by_id(self, user_id: int | str | None) -> dict[str, set[str]] | None:
        """按用户 ID 查询可见站点（供后台/流水线仅有 user_id 的场景；None 或 0 视为系统上下文不过滤）"""
        if not user_id:
            return None
        user_id = int(user_id)
        if SUPERADMIN_ROLE_CODE in self._rbac_service.get_user_role_codes(user_id):
            return None
        return self._visible_for_user(user_id)

    @staticmethod
    def is_site_allowed(
        visible: dict[str, set[str]], site_name: str, source: str = "builtin", usage: str = "search"
    ) -> bool:
        """在白名单中检查站点是否允许指定用途"""
        for key in (f"{source}:{site_name}", f"{source}:*", site_name):
            perms = visible.get(key)
            if perms and usage in perms:
                return True
        return False

    def can_access_site(
        self, user: UserContext, site_name: str, source: str = "builtin", usage: str = "search"
    ) -> bool:
        """检查用户是否可在指定用途下使用某站点"""
        visible = self.get_visible_sites(user)
        if visible is None:
            return True
        return self.is_site_allowed(visible, site_name, source, usage)

    # ---------- 管理 ----------

    def get_role_grants(self, role_id: int) -> list[dict]:
        return [self._to_dict(r) for r in self._grant_repo.get_role_grants(role_id)]

    def get_user_grants(self, user_id: int) -> list[dict]:
        return [self._to_dict(r) for r in self._grant_repo.get_user_grants(user_id)]

    def set_role_grants(self, role_id: int, grants: list[dict], granted_by: int | None = None) -> None:
        self._grant_repo.set_role_grants(role_id, grants, granted_by)
        # 角色级变更影响该角色全部用户，全量失效
        RBACSnapshotCache.clear()

    def set_user_grants(self, user_id: int, grants: list[dict], granted_by: int | None = None) -> None:
        self._grant_repo.set_user_grants(user_id, grants, granted_by)
        RBACSnapshotCache.delete(_SNAPSHOT_KEY.format(user_id=user_id))

    def invalidate(self, user_id: int | None = None) -> None:
        """主动失效（站点 PUBLIC/启停变更等场景）"""
        if user_id is not None:
            RBACSnapshotCache.delete(_SNAPSHOT_KEY.format(user_id=user_id))
        else:
            RBACSnapshotCache.clear()

    # ---------- 内部 ----------

    def _visible_for_user(self, user_id: int) -> dict[str, set[str]] | None:
        """closed 策略下计算白名单（带缓存）；open 策略返回 None 不过滤"""
        if self._is_open_policy():
            return None
        cached = RBACSnapshotCache.get(_SNAPSHOT_KEY.format(user_id=user_id))
        if cached is not None:
            return cached
        role_ids = [r.id for r in self._rbac_service.get_user_roles(user_id)]
        grants = self._grant_repo.get_user_effective_grants(user_id, role_ids)
        RBACSnapshotCache.set(_SNAPSHOT_KEY.format(user_id=user_id), grants)
        return grants

    def _is_open_policy(self) -> bool:
        policy = self._system_config.get(SystemConfigKey.SiteGrantDefaultPolicy)
        return str(policy or "open").lower() != "closed"

    @staticmethod
    def _to_dict(row) -> dict:
        return {
            "site_name": row.SITE_NAME,
            "permissions": normalize_permissions(row.PERMISSIONS),
            "granted_by": row.GRANTED_BY,
            "created_at": row.CREATED_AT.strftime("%Y-%m-%d %H:%M:%S") if row.CREATED_AT else None,
        }
