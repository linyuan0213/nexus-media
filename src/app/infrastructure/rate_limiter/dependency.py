"""FastAPI 速率限制依赖 — 按路由精细化限流."""

from fastapi import HTTPException, Request

from app.infrastructure.rate_limiter.backends import RateLimiter


class RateLimitDependency:
    """
    FastAPI 依赖注入式速率限制器

    用法：
        from app.infrastructure.rate_limiter import RateLimitDependency

        @app.post("/api/auth/login")
        async def login(
            credentials: LoginRequest,
            _rate: None = Depends(RateLimitDependency(limit=5, window=60)),
        ):
            ...

    :param limit: 窗口内最大请求次数
    :param window: 时间窗口（秒）
    :param key_prefix: 限流 key 前缀，默认使用路由路径
    """

    _limiter = RateLimiter()

    def __init__(self, limit: int = 60, window: int = 60, key_prefix: str | None = None):
        self.limit = limit
        self.window = window
        self.key_prefix = key_prefix

    async def __call__(self, request: Request) -> None:
        client_ip = self._get_client_ip(request)
        route = self.key_prefix or request.url.path
        key = f"rate_limit_dep:{client_ip}:{route}"

        if not self._limiter.is_allowed(key, self.limit, self.window):
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
            )

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
