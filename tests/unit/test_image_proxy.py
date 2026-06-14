"""图片代理核心逻辑单元测试."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.image_proxy import download_image, get_cache_path, resize_image
from app.infrastructure.image_proxy.core import download_images_concurrently


@pytest.fixture
def mock_async_http_client():
    """模拟 AsyncHttpClient，返回固定图片数据."""

    def _make_client(data: bytes | None = b"fake image data"):
        client = MagicMock()
        response = MagicMock()
        response.content = data
        response.raise_for_status = MagicMock()
        client.get = AsyncMock(return_value=response)
        client.close = AsyncMock()
        return client

    return _make_client


@pytest.mark.asyncio
async def test_download_image_success(mock_async_http_client):
    """异步下载图片成功."""
    client = mock_async_http_client(b"image bytes")
    with patch("app.infrastructure.image_proxy.core._get_client", new=AsyncMock(return_value=client)):
        result = await download_image("https://example.com/poster.jpg")

    assert result == b"image bytes"
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_image_failure(mock_async_http_client):
    """异步下载图片失败返回 None."""
    client = mock_async_http_client()
    client.get.side_effect = Exception("network error")
    with patch("app.infrastructure.image_proxy.core._get_client", new=AsyncMock(return_value=client)):
        result = await download_image("https://example.com/poster.jpg")

    assert result is None


@pytest.mark.asyncio
async def test_download_image_lock_serializes_concurrent_requests(mock_async_http_client):
    """同一图片并发下载时通过锁串行执行，不抛异常."""
    call_count = [0]

    async def tracked_get(*args, **kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.01)
        response = MagicMock()
        response.content = b"image bytes"
        response.raise_for_status = MagicMock()
        return response

    client = mock_async_http_client()
    client.get = tracked_get

    with patch("app.infrastructure.image_proxy.core._get_client", new=AsyncMock(return_value=client)):
        results = await asyncio.gather(
            download_image("https://example.com/poster.jpg"),
            download_image("https://example.com/poster.jpg"),
        )

    assert results == [b"image bytes", b"image bytes"]
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_download_images_concurrently(mock_async_http_client):
    """并发下载多张图片."""
    client = mock_async_http_client(b"data")
    with patch("app.infrastructure.image_proxy.core._get_client", new=AsyncMock(return_value=client)):
        results = await download_images_concurrently(["https://a.com/1.jpg", "https://b.com/2.jpg"], max_workers=5)

    assert len(results) == 2
    assert results["https://a.com/1.jpg"] == b"data"
    assert results["https://b.com/2.jpg"] == b"data"


@pytest.mark.asyncio
async def test_download_images_concurrently_partial_failure(mock_async_http_client):
    """并发下载部分失败."""
    client = mock_async_http_client()

    async def side_effect(url, **kwargs):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        if "fail" in url:
            raise Exception("download failed")
        response.content = b"ok"
        return response

    client.get = side_effect
    with patch("app.infrastructure.image_proxy.core._get_client", new=AsyncMock(return_value=client)):
        results = await download_images_concurrently(["https://ok.com/1.jpg", "https://fail.com/2.jpg"], max_workers=5)

    assert results["https://ok.com/1.jpg"] == b"ok"
    assert results["https://fail.com/2.jpg"] is None


def test_get_cache_path():
    """缓存路径生成包含来源，不同尺寸产生不同路径."""
    path = get_cache_path("tmdb", "abc.jpg", "w500")
    assert "tmdb" in path
    assert path.endswith(".jpg")
    path_original = get_cache_path("tmdb", "abc.jpg", "original")
    assert path != path_original


def test_resize_image_returns_original_when_no_target():
    """未指定目标尺寸时返回原数据."""
    data = b"not a real image"
    assert resize_image(data, "original") == data


@pytest.mark.skip(reason="需要真实 Pillow 图片数据")
def test_resize_image_resizes():
    """调整图片尺寸（需要真实图片数据）."""
    pass
