"""站点授权（L3）测试：repository 并集语义 + service 可见性规则."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.db.repositories.site_grant_repository import SiteGrantRepository, normalize_permissions
from app.schemas.auth import SUPERADMIN_ROLE_CODE, UserContext, system_user_context
from app.services.site_grant_service import SiteGrantService


def _user(user_id: int = 7, role_codes: list[str] | None = None) -> UserContext:
    return UserContext(
        user_id=user_id,
        username=f"u{user_id}",
        level=0,
        permissions=[],
        role_codes=role_codes or ["user"],
    )


class TestNormalizePermissions:
    def test_json_string(self):
        assert normalize_permissions('["search", "rss"]') == ["rss", "search"]

    def test_invalid_items_dropped(self):
        assert normalize_permissions(["search", "hack", None]) == ["search"]

    def test_empty_falls_back_to_search(self):
        assert normalize_permissions([]) == ["search"]
        assert normalize_permissions("not-json") == ["search"]


class TestSiteGrantRepository:
    def test_effective_grants_union(self, db_session):
        from app.db.models import RBACRole, RBACUserSite

        role = RBACRole(ROLE_NAME="vip", ROLE_CODE="vip", ROLE_LEVEL=50, STATUS=1)
        db_session.add(role)
        db_session.flush()
        from app.db.models import RBACRoleSite

        db_session.add(RBACRoleSite(ROLE_ID=role.ID, SITE_NAME="siteA", PERMISSIONS='["search"]'))
        db_session.add(RBACUserSite(USER_ID=7, SITE_NAME="siteA", PERMISSIONS='["rss"]'))
        db_session.add(RBACUserSite(USER_ID=7, SITE_NAME="siteB", PERMISSIONS='["search"]'))
        db_session.commit()

        repo = SiteGrantRepository()
        repo._session_manager = MagicMock()
        # 直接用 db_session 语义：通过 monkeypatch 方式替换 session
        from contextlib import contextmanager

        @contextmanager
        def _sess():
            yield db_session

        repo._session_manager.session_scope = _sess
        effective = repo.get_user_effective_grants(7, [role.ID])
        assert effective["siteA"] == {"search", "rss"}  # 角色级 ∪ 用户级
        assert effective["siteB"] == {"search"}


class TestSiteGrantService:
    def _make_service(self, policy="closed", grants=None, role_codes=None):
        grant_repo = MagicMock()
        grant_repo.get_user_effective_grants.return_value = grants or {}
        rbac_service = MagicMock()
        rbac_service.get_user_roles.return_value = [SimpleNamespace(id=1)]
        rbac_service.get_user_role_codes.return_value = set(role_codes or ["user"])
        system_config = MagicMock()
        system_config.get.return_value = policy
        svc = SiteGrantService(grant_repo=grant_repo, rbac_service=rbac_service, system_config=system_config)
        from app.infrastructure.cache_system import RBACSnapshotCache

        RBACSnapshotCache.clear()
        return svc

    def test_superadmin_unrestricted(self):
        svc = self._make_service()
        assert svc.get_visible_sites(system_user_context()) is None

    def test_open_policy_unrestricted(self):
        svc = self._make_service(policy="open")
        assert svc.get_visible_sites(_user()) is None

    def test_closed_policy_whitelist(self):
        svc = self._make_service(policy="closed", grants={"siteA": {"search"}})
        visible = svc.get_visible_sites(_user())
        assert visible == {"siteA": {"search"}}

    def test_by_id_system_context_unrestricted(self):
        svc = self._make_service(policy="closed")
        assert svc.get_visible_sites_by_id(None) is None
        assert svc.get_visible_sites_by_id(0) is None

    def test_by_id_superadmin_unrestricted(self):
        svc = self._make_service(policy="closed", role_codes=[SUPERADMIN_ROLE_CODE])
        assert svc.get_visible_sites_by_id(7) is None

    def test_is_site_allowed_usage_granularity(self):
        visible = {"siteA": {"search"}, "jackett:siteB": {"rss"}, "prowlarr:*": {"search", "rss"}}
        assert SiteGrantService.is_site_allowed(visible, "siteA", "builtin", "search")
        assert not SiteGrantService.is_site_allowed(visible, "siteA", "builtin", "rss")
        assert SiteGrantService.is_site_allowed(visible, "siteB", "jackett", "rss")
        assert not SiteGrantService.is_site_allowed(visible, "siteB", "jackett", "search")
        assert SiteGrantService.is_site_allowed(visible, "anything", "prowlarr", "search")
        assert not SiteGrantService.is_site_allowed(visible, "other", "builtin", "search")

    def test_set_user_grants_invalidates_cache(self):
        from app.infrastructure.cache_system import RBACSnapshotCache

        svc = self._make_service(policy="closed", grants={})
        svc.get_visible_sites(_user(7))
        assert RBACSnapshotCache.get("site_grants:7") is not None
        svc.set_user_grants(7, [{"site_name": "siteX", "permissions": ["rss"]}])
        assert RBACSnapshotCache.get("site_grants:7") is None
