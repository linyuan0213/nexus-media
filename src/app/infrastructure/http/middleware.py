"""HTTP 请求/响应中间件."""

from abc import ABC, abstractmethod

import httpx2

import log
from app.utils.log_redaction import redact_url


class HttpMiddleware(ABC):
    """HTTP 请求/响应中间件基类."""

    @abstractmethod
    def process_request(self, request: httpx2.Request) -> httpx2.Request:
        """处理请求（添加 header、签名等）."""

    @abstractmethod
    def process_response(self, response: httpx2.Response) -> httpx2.Response:
        """处理响应（日志、指标等）."""


class LoggingMiddleware(HttpMiddleware):
    """请求日志中间件."""

    def process_request(self, request: httpx2.Request) -> httpx2.Request:
        log.debug(f"[HTTP] {request.method} {redact_url(str(request.url))}")
        return request

    def process_response(self, response: httpx2.Response) -> httpx2.Response:
        log.debug(f"[HTTP] {response.status_code} {redact_url(str(response.request.url))}")
        return response
