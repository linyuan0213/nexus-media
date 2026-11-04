"""
FastAPI 图片代理路由
兼容前端通过 ImageProxy 生成的 /img/* 请求
复用 app.helper.image_proxy_core 的下载/缓存逻辑
"""

import asyncio
import base64
import io
import ipaddress
import json
import os
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from PIL import Image, ImageFilter
from starlette.responses import FileResponse, RedirectResponse, Response

import log
from app.core.constants import TMDB_IMAGE_DOMAIN
from app.core.error_codes import ErrorCode
from app.core.exceptions import DomainError, NexusError, ServiceError
from app.core.settings import settings
from app.db.repositories.config_repo_adapter import MediaServerRepositoryAdapter
from app.infrastructure.image_proxy import (
    MAX_CACHE_DAYS,
    SIZE_DIMENSIONS,
    SOURCE_DOMAINS,
    ImageProxy,
    download_image,
    get_cache_path,
    resize_image,
)
from app.infrastructure.image_proxy.referer_registry import image_referer_registry
from app.utils.json_utils import JsonUtils

router = APIRouter()

# 已配置媒体服务器主机缓存（合法内网直连放行；60s 刷新，避免每张图都查库）
_MS_HOSTS_TTL = 60.0
_ms_hosts_cache: dict = {"ts": 0.0, "hosts": set(), "ips": set()}


def _allowed_media_server_hosts() -> set[str]:
    """已配置媒体服务器（Emby/Jellyfin/Plex/FnOS）的主机名/IP 集合。"""
    now = time.time()
    if now - _ms_hosts_cache["ts"] < _MS_HOSTS_TTL:
        return _ms_hosts_cache["hosts"]
    hosts: set[str] = set()
    try:
        for item in MediaServerRepositoryAdapter().get_media_servers() or []:
            try:
                cfg = JsonUtils.loads(str(item.CONFIG)) if str(item.CONFIG or "") else {}
            except Exception:
                cfg = {}
            if not isinstance(cfg, dict):
                continue
            for key in ("host", "play_host"):
                value = cfg.get(key)
                if isinstance(value, str) and value:
                    host = urllib.parse.urlparse(value if "://" in value else f"//{value}").hostname
                    if host:
                        hosts.add(host)
    except Exception as e:  # noqa: BLE001
        log.debug(f"[Img]读取媒体服务器主机失败：{e}")
    # 解析出对应 IP：覆盖「配置写域名、图片用 IP（或反之）」的别名场景
    ips: set[str] = set()
    for host in hosts:
        try:
            ips.update(str(info[4][0]) for info in socket.getaddrinfo(host, None))
        except OSError:
            continue
    _ms_hosts_cache["ts"] = now
    _ms_hosts_cache["hosts"] = hosts
    _ms_hosts_cache["ips"] = ips
    return hosts


def _is_allowed_library_host(host: str) -> bool:
    """图片主机是否为已配置媒体服务器（主机名直接命中，或解析 IP 命中别名）。"""
    if not host:
        return False
    allowed_hosts = _allowed_media_server_hosts()
    if host in allowed_hosts:
        return True
    _allowed_media_server_hosts()  # 确保 ips 已计算
    try:
        resolved = {str(info[4][0]) for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(resolved & _ms_hosts_cache["ips"])


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _guard_image_url(url: str) -> None:
    """SSRF 防护：仅允许 http(s)，且目标主机不得解析到内网/保留地址。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise NexusError("非法图片地址", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=400)
    host = (parsed.hostname or "").strip().strip("[]")
    if not host or host.lower() == "localhost":
        raise NexusError("不允许访问的图片地址", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=400)
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise NexusError("图片地址无法解析", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=400) from e
    if not infos or any(_is_blocked_ip(str(info[4][0])) for info in infos):
        raise NexusError("不允许访问的图片地址", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=400)


def _to_jpeg_bytes(data: bytes) -> bytes:
    """第三方消息渠道兼容：统一转 JPEG."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format == "JPEG":
                return data
            output = io.BytesIO()
            img.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.debug(f"[ImageProxy]转 JPEG 失败: {exc}")
        return data


async def _serve_image(
    cache_path: str,
    image_url: str,
    size: str | None = None,
    referer: str | None = None,
    media_type: str = "image/jpeg",
    downloader=None,
    convert_jpeg: bool = False,
):
    """FastAPI 版本的缓存检查/下载/返回图片"""
    # 检查缓存（30 天过期），空缓存直接删除重下
    if os.path.exists(cache_path):
        try:
            stat = os.stat(cache_path)
            if stat.st_size > 0 and time.time() - stat.st_mtime < MAX_CACHE_DAYS * 24 * 3600:
                if convert_jpeg:
                    with open(cache_path, "rb") as handle:
                        cached_data = handle.read()
                    jpeg_data = await asyncio.to_thread(_to_jpeg_bytes, cached_data)
                    if jpeg_data != cached_data:
                        with open(cache_path, "wb") as handle:
                            handle.write(jpeg_data)
                    return Response(jpeg_data, media_type="image/jpeg")
                return FileResponse(cache_path, media_type=media_type)
            else:
                os.remove(cache_path)
        except (ServiceError, DomainError) as e:
            log.error(f"[ImageProxy]读取缓存失败: {e.message}")
        except Exception as e:
            log.error(f"[ImageProxy]读取缓存失败: {str(e)}")

    # 下载图片（同步 downloader 放线程池，避免阻塞事件循环）
    if downloader:
        image_data = await asyncio.to_thread(downloader, image_url)
    else:
        image_data = await download_image(image_url, referer=referer)
    if not image_data or len(image_data) < 100:
        log.error(f"[ImageProxy]下载内容为空或过小: {image_url}")
        raise NexusError("获取图片失败", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=404)

    # 调整尺寸（PIL CPU 密集，放线程池）
    if size and size != "original":
        image_data = await asyncio.to_thread(resize_image, image_data, size)
    if convert_jpeg:
        image_data = await asyncio.to_thread(_to_jpeg_bytes, image_data)

    # 保存到缓存
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(image_data)
    except (ServiceError, DomainError) as e:
        log.error(f"[ImageProxy]保存缓存失败: {e.message}")
    except Exception as e:
        log.error(f"[ImageProxy]保存缓存失败: {str(e)}")

    return Response(image_data, media_type=media_type)


@router.get("/tmdb/{size}/{img_path:path}", summary="代理 TMDB 图片")
async def proxy_tmdb_image(size: str, img_path: str):
    """代理 TMDB 图片"""
    if size not in SIZE_DIMENSIONS:
        size = "w500"
    cache_path = get_cache_path("tmdb", img_path, size)
    original_url = f"https://{TMDB_IMAGE_DOMAIN}/t/p/original/{img_path}"
    return await _serve_image(cache_path, original_url, size)


@router.get("/douban/{img_path:path}", summary="代理豆瓣图片")
async def proxy_douban_image(img_path: str):
    """代理豆瓣图片"""
    decoded_path = urllib.parse.unquote(img_path)
    cache_path = get_cache_path("douban", decoded_path)
    if decoded_path.startswith("http"):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['douban']}/{decoded_path}"
    _guard_image_url(image_url)
    return await _serve_image(cache_path, image_url, referer="https://movie.douban.com", convert_jpeg=True)


@router.get("/bgm/{img_path:path}", summary="代理 Bangumi 图片")
async def proxy_bgm_image(img_path: str):
    """代理 Bangumi 图片"""
    decoded_path = urllib.parse.unquote(img_path)
    cache_path = get_cache_path("bgm", decoded_path)
    if decoded_path.startswith("http"):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['bgm']}/{decoded_path}"
    _guard_image_url(image_url)
    return await _serve_image(cache_path, image_url)


def _face_box(data: bytes) -> tuple[int, int, int, int] | None:
    verify_url = os.environ.get("NEXUS_VERIFY_URL", "http://nexus-verify:9300").rstrip("/")
    try:
        request = urllib.request.Request(
            f"{verify_url}/face/bbox",
            data=json.dumps({"image_b64": base64.b64encode(data).decode()}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode() or "{}")
    except Exception:  # noqa: BLE001 - verify 不可用时回退裁切
        return None
    faces = payload.get("faces") or []
    if not faces:
        return None
    face = max(faces, key=lambda item: item.get("width", 0) * item.get("height", 0))
    return int(face["x"]), int(face["y"]), int(face["width"]), int(face["height"])


def _crop_poster_bytes(data: bytes, mode: str) -> bytes:
    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
        if mode == "none" or width <= height * 1.15:
            return data
        target_w = max(1, int(height * 0.71))
        if mode == "face":
            face = _face_box(data)
            if face:
                fx, _, fw, _ = face
                center_x = fx + fw // 2
                left = max(0, min(center_x - int(target_w * 0.38), width - target_w))
                output = io.BytesIO()
                img.crop((left, 0, left + target_w, height)).save(output, format="JPEG", quality=92)
                return output.getvalue()
            # 人脸模型不可用/未检测到脸时居中裁切；人物主体通常在中央，
            # 回退右侧只会得到空白背景。
            left = max(0, (width - target_w) // 2)
        else:
            left = max(0, width - target_w)
        output = io.BytesIO()
        img.crop((left, 0, left + target_w, height)).save(output, format="JPEG", quality=92)
        return output.getvalue()


@router.get("/crop", summary="按裁剪策略代理海报")
async def proxy_poster(url: str, mode: str = "face"):
    """下载后按 face/right/none 裁剪，供插件按海报配置使用."""
    _guard_image_url(url)
    cache_path = get_cache_path("poster", f"v4:{mode}:{url}")
    if os.path.exists(cache_path):
        return FileResponse(cache_path, media_type="image/jpeg")
    data = await download_image(url)
    if not data:
        raise NexusError("获取图片失败", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=404)
    try:
        data = await asyncio.to_thread(_crop_poster_bytes, data, mode)
    except Exception as e:  # noqa: BLE001 - 裁剪失败返回原图
        log.debug(f"[Img]海报裁剪失败 {url}: {e}")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as handle:
        handle.write(data)
    return Response(data, media_type="image/jpeg")


@router.get("/library/{img_url:path}", summary="代理媒体库图片")
async def proxy_library_image(request: Request, img_url: str, server_id: int | None = None):
    """代理媒体库内网图片"""
    decoded_url = urllib.parse.unquote(img_url)
    # 重新附加查询参数（如 Plex 的 X-Plex-Token）
    if request.query_params:
        separator = "&" if "?" in decoded_url else "?"
        query_string = str(request.query_params)
        decoded_url += separator + query_string
    cache_path = get_cache_path("library", decoded_url)
    if "/v/api/v1/sys/img/" in decoded_url:
        ms = request.app.state.context.media_server
        return await _serve_image(cache_path, decoded_url, downloader=lambda u: ms.download_image(u, server_id))
    # 已配置媒体服务器的内网地址为合法来源，放行；其余外部地址仍做 SSRF 校验
    decoded_host = urllib.parse.urlparse(decoded_url).hostname or ""
    if _is_allowed_library_host(decoded_host):
        return await _serve_image(cache_path, decoded_url)
    _guard_image_url(decoded_url)
    return await _serve_image(
        cache_path,
        decoded_url,
        referer=image_referer_registry.resolve(decoded_url),
    )


_LOCAL_POSTER_NAMES = frozenset({"poster.jpg", "poster.png", "fanart.jpg", "thumb.jpg", "background.jpg"})
_BLUR_MAX_DEPTH = 5


def _local_poster_roots() -> tuple[str, ...]:
    """本地海报允许的媒体库根目录（配置优先，兼容默认 /Media 挂载）."""
    roots: list[str] = []
    configured = str((settings.get("media") or {}).get("media_default_path") or "").strip()
    if configured:
        roots.append(os.path.realpath(configured))
    for fallback in ("/Media",):
        real = os.path.realpath(fallback)
        if real not in roots:
            roots.append(real)
    return tuple(roots)


def _safe_local_poster(path: str) -> str:
    """校验媒体目录内的海报路径，返回 realpath；非法时返回空字符串."""
    candidate = os.path.realpath(urllib.parse.unquote(str(path or "")))
    if os.path.basename(candidate).lower() not in _LOCAL_POSTER_NAMES:
        return ""
    if not any(candidate == root or candidate.startswith(root + os.sep) for root in _local_poster_roots()):
        return ""
    return candidate if os.path.isfile(candidate) else ""


@router.get("/poster", summary="本地媒体海报")
async def local_poster(path: str):
    """返回媒体目录内已裁剪的海报，仅允许安全的图片文件名."""
    decoded = _safe_local_poster(path)
    if not decoded:
        raise NexusError("图片不存在", http_status=404)
    return FileResponse(decoded)


def _resolve_blur_source(url: str, depth: int = 0) -> tuple[str, str]:
    """把嵌套的本地代理 URL 还原为可下载的远程 URL 或本地海报路径.

    :return: (remote_url, local_path)；二者只会有一个非空，remote_url 也可能为空。
    """
    decoded = urllib.parse.unquote(str(url or ""))
    if depth > _BLUR_MAX_DEPTH:
        return "", ""
    if decoded.startswith("/img/blur?"):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(decoded).query)
        nested = (query.get("url") or [""])[0]
        return _resolve_blur_source(nested, depth + 1) if nested else ("", "")
    if decoded.startswith("/img/library/"):
        inner = urllib.parse.unquote(decoded[len("/img/library/") :])
        return _resolve_blur_source(inner, depth + 1)
    if decoded.startswith("/img/crop?"):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(decoded).query)
        nested = (query.get("url") or [""])[0]
        return _resolve_blur_source(nested, depth + 1) if nested else ("", "")
    if decoded.startswith("/img/poster?"):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(decoded).query)
        local = _safe_local_poster((query.get("path") or [""])[0])
        return ("", local) if local else ("", "")
    if decoded.startswith("/img/tmdb/"):
        rest = decoded[len("/img/tmdb/") :]
        _, _, img_path = rest.partition("/")
        return f"https://{TMDB_IMAGE_DOMAIN}/t/p/original/{img_path}", ""
    if decoded.startswith("/img/douban/"):
        inner = urllib.parse.unquote(decoded[len("/img/douban/") :])
        if inner.startswith(("http://", "https://")):
            return inner, ""
        return f"https://{SOURCE_DOMAINS['douban']}/{inner.lstrip('/')}", ""
    if decoded.startswith("/img/bgm/"):
        inner = urllib.parse.unquote(decoded[len("/img/bgm/") :])
        if inner.startswith(("http://", "https://")):
            return inner, ""
        return f"https://{SOURCE_DOMAINS['bgm']}/{inner.lstrip('/')}", ""
    if decoded.startswith("/") and not decoded.startswith("/img/"):
        # 插件本地海报路径：只允许媒体库内已知海报文件，禁止任意本地文件读取。
        local = _safe_local_poster(decoded)
        return ("", local) if local else ("", "")
    return decoded, ""


@router.get("/blur", summary="图片模糊代理")
async def proxy_blur_image(url: str, radius: int = 20):
    """通用图片模糊代理，供插件实现 SFW 展示；不包含任何内容画像判断."""
    source, local_poster = _resolve_blur_source(url)
    if not source and not local_poster:
        raise NexusError("非法图片地址", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=400)
    try:
        radius = max(1, min(int(radius or 20), 60))
    except (TypeError, ValueError):
        radius = 20
    cache_key = source or local_poster
    cache_path = get_cache_path("blur", f"{urllib.parse.quote(cache_key, safe='')}-{radius}")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return FileResponse(cache_path, media_type="image/jpeg")
    if local_poster:
        try:
            data = await asyncio.to_thread(Path(local_poster).read_bytes)
        except OSError:
            data = b""
    else:
        _guard_image_url(source)
        data = await download_image(source, referer=image_referer_registry.resolve(source))
    if not data:
        raise NexusError("获取图片失败", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=404)

    def _blur(payload: bytes) -> bytes:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        image = image.filter(ImageFilter.GaussianBlur(radius=radius))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88)
        return output.getvalue()

    blurred = await asyncio.to_thread(_blur, data)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as handle:
        handle.write(blurred)
    return Response(blurred, media_type="image/jpeg")


@router.get("", summary="图片代理重定向")
@router.get("/", summary="图片代理重定向（兼容斜杠）")
def proxy_image_redirect(request: Request, url: str | None = None):
    """
    旧格式兼容：/img?url=...
    1. /img?url=/img/tmdb/xxx.jpg -> 重定向到 /img/tmdb/xxx.jpg
    2. /img?url=https://... -> 转换为代理路径后重定向
    """
    if not url:
        raise NexusError("参数错误", errcode=ErrorCode.PARAM_VALIDATION_FAILED, http_status=400)

    # 如果 url 是本地代理路径（以 /img/ 开头），重定向到新路由
    if url.startswith("/img/"):
        return RedirectResponse(url=url, status_code=307)

    # 外部图片 URL：转换为代理路径后重定向
    try:
        proxy_url = ImageProxy.get_proxy_image_url(url, use_proxy=True)
    except (ServiceError, DomainError):
        proxy_url = None
    except Exception:
        proxy_url = None

    if proxy_url and proxy_url.startswith("/img/"):
        return RedirectResponse(url=proxy_url, status_code=307)

    # 兜底：无法生成代理路径时，直接代理
    raise NexusError("无法处理该图片 URL", errcode=ErrorCode.IMAGE_FETCH_FAILED, http_status=404)


@router.get("/favicon/external/{encoded_url:path}", summary="代理外部 favicon URL")
async def proxy_favicon_external(encoded_url: str):
    """代理外部 favicon URL."""
    favicon_url = urllib.parse.unquote(encoded_url)
    _guard_image_url(favicon_url)
    cache_path = get_cache_path("favicon", urllib.parse.quote(favicon_url, safe=""))
    return await _serve_image(cache_path, favicon_url, referer=favicon_url, media_type="image/x-icon")


@router.get("/favicon/{domain:path}", summary="代理站点 favicon")
async def proxy_favicon(domain: str):
    """代理站点 favicon.ico，下载到本地缓存并返回."""
    favicon_url = f"https://{domain}/favicon.ico"
    _guard_image_url(favicon_url)
    cache_path = get_cache_path("favicon", domain)
    return await _serve_image(cache_path, favicon_url, referer=f"https://{domain}", media_type="image/x-icon")


@router.get("/agent/{name}", summary="Agent 浏览器截图")
async def agent_screenshot(name: str):
    """返回 Agent 浏览器工具保存的截图（数据目录 static/agent，防路径穿越）"""
    safe = Path(name).name
    if not safe.endswith(".png"):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = Path(settings.data_path) / "static" / "agent" / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type="image/png")
