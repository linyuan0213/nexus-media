from typing import Any

from pydantic import BaseModel


class CommonResponse(BaseModel):
    """通用 API 响应格式"""

    code: int = 0
    data: Any = None
    message: str = ""


class HealthServiceStatus(BaseModel):
    """单个服务健康状态"""

    status: str = "unknown"
    detail: str = ""


class HealthCheckResponse(BaseModel):
    """健康检查响应"""

    status: str = "ok"
    version: str = ""
    database: HealthServiceStatus = HealthServiceStatus()
    redis: HealthServiceStatus = HealthServiceStatus()
    services: dict[str, HealthServiceStatus] = {}
