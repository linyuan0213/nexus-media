"""FastAPI 速率限制中间件."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import log
from app.infrastructure.rate_limiter.backends import RateLimiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    全局 API 速率限制中间件

    基于客户端 IP 的滑动窗口限流，Redis 可用时分布式生效，
    否则降级为单进程内存限流。

    豁免路径：
    - /health  健康检查
    - /static  静态文件
    - /docs /openapi.json  Swagger
    """

    _EXEMPT_PATHS = {"/health", "/static", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, limit: int = 60, window: int = 60):
        super().__init__(app)
        self._limiter = RateLimiter()
        self._limit = limit
        self._window = window

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 豁免路径
        if any(path.startswith(exempt) for exempt in self._EXEMPT_PATHS):
            return await call_next(request)

        # 提取客户端 IP
        client_ip = self._get_client_ip(request)
        key = f"rate_limit:{client_ip}:{path}"

        if not self._limiter.is_allowed(key, self._limit, self._window):
            log.warn(f"[RateLimit]IP {client_ip} 请求 {path} 触发限流")
            return Response(
                content='{"detail":"请求过于频繁，请稍后再试"}',
                status_code=429,
                media_type="application/json",
            )

        return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """获取真实客户端 IP"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-Ip")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"
