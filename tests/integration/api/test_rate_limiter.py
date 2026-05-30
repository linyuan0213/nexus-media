"""速率限制中间件集成测试."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.infrastructure.rate_limiter.middleware import RateLimitMiddleware


@pytest.fixture
def mock_redis_unavailable():
    """模拟 Redis 不可用，使用内存后端"""
    with patch("app.infrastructure.rate_limiter.backends.RedisStore") as mock_cls:
        mock_store = mock_cls.return_value
        mock_store.is_available.return_value = False
        yield


class TestRateLimitMiddleware:
    def test_exempt_paths_bypass_limit(self, mock_redis_unavailable):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=1, window=60)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        client = TestClient(app)
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200

    def test_blocks_when_limit_reached(self, mock_redis_unavailable):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=2, window=60)

        @app.get("/api/test")
        def test_endpoint():
            return {"data": "ok"}

        client = TestClient(app)
        assert client.get("/api/test").status_code == 200
        assert client.get("/api/test").status_code == 200
        response = client.get("/api/test")
        assert response.status_code == 429
        assert "请求过于频繁" in response.text

    def test_uses_x_forwarded_for_header(self, mock_redis_unavailable):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=2, window=60)

        @app.get("/api/test")
        def test_endpoint():
            return {"data": "ok"}

        client = TestClient(app)
        headers = {"X-Forwarded-For": "1.2.3.4"}
        assert client.get("/api/test", headers=headers).status_code == 200
        assert client.get("/api/test", headers=headers).status_code == 200
        assert client.get("/api/test", headers=headers).status_code == 429

    def test_different_ips_have_independent_limits(self, mock_redis_unavailable):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=2, window=60)

        @app.get("/api/test")
        def test_endpoint():
            return {"data": "ok"}

        client_a = TestClient(app, headers={"X-Forwarded-For": "1.1.1.1"})
        client_b = TestClient(app, headers={"X-Forwarded-For": "2.2.2.2"})

        assert client_a.get("/api/test").status_code == 200
        assert client_a.get("/api/test").status_code == 200
        assert client_a.get("/api/test").status_code == 429

        assert client_b.get("/api/test").status_code == 200
        assert client_b.get("/api/test").status_code == 200

    def test_static_path_exempt(self, mock_redis_unavailable):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=1, window=60)

        @app.get("/static/file.txt")
        def static_file():
            return {"file": "content"}

        client = TestClient(app)
        for _ in range(5):
            assert client.get("/static/file.txt").status_code == 200
