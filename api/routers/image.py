"""
FastAPI 图片代理路由
兼容前端通过 ImageProxyHelper 生成的 /img/* 请求
复用 app.helper.image_proxy_core 的下载/缓存逻辑
"""
import os
import time
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse, RedirectResponse, Response

import log
from app.helper.image_proxy_core import (
    MAX_CACHE_DAYS,
    SIZE_DIMENSIONS,
    SOURCE_DOMAINS,
    download_image,
    get_cache_path,
    resize_image,
)

router = APIRouter()


def _serve_image(cache_path: str, image_url: str, size: str | None = None, referer: str | None = None):
    """FastAPI 版本的缓存检查/下载/返回图片"""
    # 检查缓存（30 天过期），空缓存直接删除重下
    if os.path.exists(cache_path):
        try:
            stat = os.stat(cache_path)
            if stat.st_size > 0 and time.time() - stat.st_mtime < MAX_CACHE_DAYS * 24 * 3600:
                return FileResponse(cache_path, media_type="image/jpeg")
            else:
                os.remove(cache_path)
        except Exception as e:
            log.error(f"【ImageProxy】读取缓存失败: {str(e)}")

    # 下载图片
    image_data = download_image(image_url, referer=referer)
    if not image_data or len(image_data) < 100:
        log.error(f"【ImageProxy】下载内容为空或过小: {image_url}")
        raise HTTPException(status_code=404, detail="获取图片失败")

    # 调整尺寸
    if size and size != "original":
        image_data = resize_image(image_data, size)

    # 保存到缓存
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(image_data)
    except Exception as e:
        log.error(f"【ImageProxy】保存缓存失败: {str(e)}")

    return Response(image_data, media_type="image/jpeg")


@router.get("/tmdb/{size}/{img_path:path}")
def proxy_tmdb_image(size: str, img_path: str):
    """代理 TMDB 图片"""
    if size not in SIZE_DIMENSIONS:
        size = "w500"
    cache_path = get_cache_path("tmdb", img_path, size)
    from app.core.constants import TMDB_IMAGE_DOMAIN
    original_url = f"https://{TMDB_IMAGE_DOMAIN}/t/p/original/{img_path}"
    return _serve_image(cache_path, original_url, size)


@router.get("/douban/{img_path:path}")
def proxy_douban_image(img_path: str):
    """代理豆瓣图片"""
    decoded_path = urllib.parse.unquote(img_path)
    cache_path = get_cache_path("douban", decoded_path)
    if decoded_path.startswith("http"):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['douban']}/{decoded_path}"
    return _serve_image(cache_path, image_url, referer="https://movie.douban.com")


@router.get("/bgm/{img_path:path}")
def proxy_bgm_image(img_path: str):
    """代理 Bangumi 图片"""
    decoded_path = urllib.parse.unquote(img_path)
    cache_path = get_cache_path("bgm", decoded_path)
    if decoded_path.startswith("http"):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['bgm']}/{decoded_path}"
    return _serve_image(cache_path, image_url)


@router.get("/library/{img_url:path}")
def proxy_library_image(request: Request, img_url: str):
    """代理媒体库内网图片"""
    decoded_url = urllib.parse.unquote(img_url)
    # 重新附加查询参数（如 Plex 的 X-Plex-Token）
    if request.query_params:
        separator = "&" if "?" in decoded_url else "?"
        query_string = str(request.query_params)
        decoded_url += separator + query_string
    cache_path = get_cache_path("library", decoded_url)
    return _serve_image(cache_path, decoded_url)


@router.get("")
def proxy_image_redirect(request: Request, url: str | None = None):
    """
    旧格式兼容：/img?url=...
    1. /img?url=/img/tmdb/xxx.jpg -> 重定向到 /img/tmdb/xxx.jpg
    2. /img?url=https://... -> 转换为代理路径后重定向
    """
    if not url:
        raise HTTPException(status_code=400, detail="参数错误")

    # 如果 url 是本地代理路径（以 /img/ 开头），重定向到新路由
    if url.startswith("/img/"):
        return RedirectResponse(url=url, status_code=307)

    # 外部图片 URL：转换为代理路径后重定向
    from app.helper.image_proxy_helper import ImageProxyHelper
    try:
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
    except Exception:
        proxy_url = None

    if proxy_url and proxy_url.startswith("/img/"):
        return RedirectResponse(url=proxy_url, status_code=307)

    # 兜底：无法生成代理路径时，直接代理
    raise HTTPException(status_code=404, detail="无法处理该图片 URL")
