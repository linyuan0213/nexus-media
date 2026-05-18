"""
FastAPI 启动集成测试
验证 FastAPI 应用可正确启动并响应基础请求
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class TestFastAPIStartup:
    @patch("app.services.system_service.SystemLifecycleService")
    def test_health_endpoint(self, mock_cls):
        """健康检查端点（mock 后台服务避免启动阻塞）"""
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["version"] == "3.8.0"

    def test_fastapi_app_title(self):
        """应用元数据验证"""
        assert app.title == "Nexus Media API"
        assert "现代化 FastAPI" in app.description

    def test_all_routers_registered(self):
        """验证所有路由已注册"""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        # 检查至少有一个 api 前缀的路由
        api_routes = [r for r in routes if r.startswith("/api/")]
        assert len(api_routes) > 0, "应该有 API 路由被注册"

        # 检查各领域的典型路由
        expected_prefixes = [
            "/api/system/",
            "/api/site/",
            "/api/download/",
            "/api/rss/",
            "/api/sync/",
            "/api/brush/",
            "/api/filter/",
            "/api/scheduler/",
            "/api/plugin/",
            "/api/userrss/",
            "/api/words/",
            "/api/media/",
            "/api/rbac/",
        ]
        for prefix in expected_prefixes:
            matching = [r for r in api_routes if r.startswith(prefix)]
            assert len(matching) > 0, f"缺少 {prefix} 前缀的路由"
