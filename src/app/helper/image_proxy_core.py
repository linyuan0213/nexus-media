"""
图片代理核心逻辑（与 Web 框架无关）
供 Flask 蓝图和 FastAPI 路由共用。
"""

import hashlib
import os
import threading
import time
import urllib.parse

from app.core.root_path import get_project_root
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import requests
from PIL import Image
from requests.adapters import HTTPAdapter

import log
from app.core.constants import TMDB_IMAGE_DOMAIN
from app.utils.config_tools import get_proxies

# 下载任务锁，防止重复下载同一个图片
_download_locks = {}
_download_locks_lock = threading.Lock()

# 缓存目录（与 Flask 侧保持一致）
CACHE_DIR = os.path.join(get_project_root(), "static", "img_cache")
MAX_CACHE_SIZE = 1024 * 1024 * 1024  # 1GB 最大缓存
MAX_CACHE_DAYS = 30  # 缓存30天

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)

# 图片尺寸映射
SIZE_DIMENSIONS = {"w92": 92, "w154": 154, "w185": 185, "w342": 342, "w500": 500, "w780": 780, "original": None}

# 来源域名映射
SOURCE_DOMAINS = {"tmdb": TMDB_IMAGE_DOMAIN, "douban": "img9.doubanio.com", "bgm": "lain.bgm.tv"}

# 连接池 Session 管理
_session_pool = {}
_session_lock = threading.Lock()


def _get_session(domain):
    """获取或创建带连接池的 Session"""
    with _session_lock:
        if domain not in _session_pool:
            session = requests.Session()
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=3, pool_block=False)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            _session_pool[domain] = session
        return _session_pool[domain]


def _get_cache_path(source, url_path, size=None):
    """生成缓存文件路径"""
    cache_key = f"{source}/{size or 'original'}/{url_path}"
    url_hash = hashlib.md5(cache_key.encode(), usedforsecurity=False).hexdigest()
    date_dir = time.strftime("%Y%m", time.localtime())
    cache_dir = os.path.join(CACHE_DIR, source, date_dir)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{url_hash}.jpg")


def _clean_old_cache():
    """清理过期缓存"""
    try:
        now = time.time()
        total_size = 0
        for root, _dirs, files in os.walk(CACHE_DIR):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    stat = os.stat(filepath)
                    file_age = now - stat.st_mtime
                    if file_age > MAX_CACHE_DAYS * 24 * 3600:
                        os.remove(filepath)
                        log.debug(f"[ImageProxy]删除过期缓存: {filepath}")
                    else:
                        total_size += stat.st_size
                except Exception as e:
                    log.error(f"[ImageProxy]清理缓存失败: {str(e)}")

        if total_size > MAX_CACHE_SIZE:
            files = []
            for root, _dirs, filenames in os.walk(CACHE_DIR):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    try:
                        stat = os.stat(filepath)
                        files.append((filepath, stat.st_mtime, stat.st_size))
                    except Exception:
                        pass
            files.sort(key=lambda x: x[1])
            for filepath, _mtime, size in files:
                if total_size <= MAX_CACHE_SIZE:
                    break
                try:
                    os.remove(filepath)
                    total_size -= size
                    log.debug(f"[ImageProxy]删除旧缓存释放空间: {filepath}")
                except Exception:
                    pass
    except Exception as e:
        log.error(f"[ImageProxy]清理缓存失败: {str(e)}")


def _download_image(url, timeout=10, referer=None):
    """
    下载图片 - 使用连接池和并发控制
    """
    cache_key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()

    with _download_locks_lock:
        if cache_key in _download_locks:
            lock = _download_locks[cache_key]
        else:
            lock = threading.Lock()
            _download_locks[cache_key] = lock

    with lock:
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc
            session = _get_session(domain)

            try:
                proxies = get_proxies() or None
            except Exception:
                proxies = None

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            if referer:
                headers["Referer"] = referer

            response = session.get(
                url, proxies=proxies, headers=headers, timeout=timeout, verify=False, allow_redirects=True
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            log.error(f"[ImageProxy]下载图片失败 {url}: {str(e)}")
            return None
        finally:
            with _download_locks_lock:
                if cache_key in _download_locks:
                    del _download_locks[cache_key]


def download_images_concurrently(urls, referer=None, max_workers=10):
    """并发下载多张图片"""
    results = {}

    def download_single(url):
        return url, _download_image(url, referer=referer)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_single, url): url for url in urls}
        for future in as_completed(futures):
            url, data = future.result()
            results[url] = data

    return results


def _resize_image(image_data, target_size):
    """调整图片尺寸"""
    try:
        img = Image.open(BytesIO(image_data))
        target_width = SIZE_DIMENSIONS.get(target_size)
        if not target_width or target_width >= img.width:
            return image_data

        ratio = target_width / img.width
        target_height = int(img.height * ratio)
        img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        output = BytesIO()
        img_resized.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()
    except Exception as e:
        log.error(f"[ImageProxy]调整图片尺寸失败: {str(e)}")
        return image_data


def get_cache_path(source, url_path, size=None):
    """外部 API：获取缓存路径"""
    return _get_cache_path(source, url_path, size)


def download_image(url, timeout=10, referer=None):
    """外部 API：下载图片"""
    return _download_image(url, timeout=timeout, referer=referer)


def resize_image(image_data, target_size):
    """外部 API：调整图片尺寸"""
    return _resize_image(image_data, target_size)


def clean_old_cache():
    """外部 API：清理过期缓存"""
    _clean_old_cache()
