"""可见站点接口：用途粒度叠加站点实际能力（RSS 源）测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_app_context, get_current_user, get_site_service
from api.routers import site as site_router
from app.schemas.auth import UserContext


def _client(grants, indexers, rss_sites, user=None):
    app = FastAPI()
    app.include_router(site_router.router, prefix="/api/site")
    ctx = SimpleNamespace(
        site_grant_service=MagicMock(),
        indexer_service=SimpleNamespace(indexer=MagicMock()),
    )
    ctx.site_grant_service.get_visible_sites.return_value = grants
    ctx.indexer_service.indexer.get_indexers_with_source.return_value = indexers
    site_svc = MagicMock()
    site_svc.get_sites.return_value = [{"name": n} for n in rss_sites]

    app.dependency_overrides[get_app_context] = lambda: ctx
    app.dependency_overrides[get_site_service] = lambda: site_svc
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


_INDEXERS = [
    {"name": "siteA", "source": "builtin", "builtin": True},
    {"name": "siteB", "source": "builtin", "builtin": True},
]


class TestVisibleSitesCapability:
    def test_rss_permission_requires_rss_source(self):
        """未配置 RSS 源的站点不展示 rss 用途"""
        user = UserContext(user_id=2, username="u", level=100, permissions=[], role_codes=["user"])
        c = _client(
            grants={"siteA": {"search", "rss"}, "siteB": {"search", "rss"}},
            indexers=_INDEXERS,
            rss_sites=["siteA"],  # 只有 A 配了 RSS 源
            user=user,
        )
        data = c.get("/api/site/sites/visible").json()["data"]
        by_name = {d["name"]: d["permissions"] for d in data}
        assert by_name["siteA"] == ["rss", "search"]
        assert by_name["siteB"] == ["search"]

    def test_no_grant_for_capability_only_site_dropped(self):
        """只有 rss 授权但站点无 RSS 源 → 站点整体不可用，不展示"""
        user = UserContext(user_id=2, username="u", level=100, permissions=[], role_codes=["user"])
        c = _client(
            grants={"siteB": {"rss"}},
            indexers=_INDEXERS,
            rss_sites=["siteA"],
            user=user,
        )
        data = c.get("/api/site/sites/visible").json()["data"]
        assert {d["name"] for d in data} == set()

    def test_superadmin_permissions_reflect_capability(self):
        user = UserContext(user_id=1, username="admin", level=0, permissions=["*"], role_codes=["superadmin"])
        c = _client(grants=None, indexers=_INDEXERS, rss_sites=["siteA"], user=user)
        data = c.get("/api/site/sites/visible").json()["data"]
        by_name = {d["name"]: d["permissions"] for d in data}
        assert by_name["siteA"] == ["rss", "search"]
        assert by_name["siteB"] == ["search"]


class TestIndexIdAllowed:
    """站点读接口按授权站点判定（site:view 用户只见被授权站点）"""

    def _ctx(self, indexers):
        return SimpleNamespace(indexer_service=SimpleNamespace(get_indexers=lambda check=False: indexers))

    def test_none_allowed_means_unrestricted(self):
        assert site_router._index_id_allowed(None, self._ctx([]), "anything") is True

    def test_matches_by_name(self):
        ctx = self._ctx([SimpleNamespace(id="builtin:mteam", name="mteam")])
        assert site_router._index_id_allowed({"mteam"}, ctx, "builtin:mteam") is True
        assert site_router._index_id_allowed({"other"}, ctx, "builtin:mteam") is False

    def test_fallback_prefix_parse(self):
        ctx = self._ctx([])
        assert site_router._index_id_allowed({"mteam"}, ctx, "jackett:mteam") is True
        assert site_router._index_id_allowed({"other"}, ctx, "jackett:mteam") is False
