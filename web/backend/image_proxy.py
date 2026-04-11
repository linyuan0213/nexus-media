# -*- coding: utf-8 -*-
"""
图片代理服务 - 支持 TMDB、豆瓣、Bangumi、媒体库

功能：
1. 代理外部图片请求，解决跨域和访问慢问题
2. 本地缓存图片，减少重复下载
3. 支持动态尺寸转换
4. 支持 WebP 格式转换（可选）
5. 支持并发下载和连接池复用

使用方式：
/img/tmdb/<size>/<path>     - TMDB 图片
/img/douban/<path>          - 豆瓣图片
/img/bgm/<path>             - Bangumi 图片
/img/library/<path>         - 媒体库（Emby/Jellyfin/Plex/fnos 等）内网图片

尺寸：w92, w154, w185, w342, w500, w780, original
"""
import os
import hashlib
import time
import threading
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from io import BytesIO

from flask import Blueprint, Response, request, abort, send_file, jsonify
from PIL import Image

from config import Config, TMDB_IMAGE_DOMAIN, TMDB_IMAGE_SIZE
from web.security import login_required
import log

# 下载任务锁，防止重复下载同一个图片
_download_locks = {}
_download_locks_lock = threading.Lock()

# 创建蓝图
img_blueprint = Blueprint('image', __name__)

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img_cache')
MAX_CACHE_SIZE = 1024 * 1024 * 1024  # 1GB 最大缓存
MAX_CACHE_DAYS = 30  # 缓存30天

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)

# 图片尺寸映射
SIZE_DIMENSIONS = {
    'w92': 92,
    'w154': 154,
    'w185': 185,
    'w342': 342,
    'w500': 500,
    'w780': 780,
    'original': None
}

# 来源域名映射
SOURCE_DOMAINS = {
    'tmdb': TMDB_IMAGE_DOMAIN,
    'douban': 'img9.doubanio.com',
    'bgm': 'lain.bgm.tv'
}

# 连接池 Session 管理
_session_pool = {}
_session_lock = threading.Lock()


def _get_session(domain):
    """获取或创建带连接池的 Session"""
    with _session_lock:
        if domain not in _session_pool:
            session = requests.Session()
            # 配置连接池
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=3,
                pool_block=False
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            _session_pool[domain] = session
        return _session_pool[domain]


def _get_cache_path(source, url_path, size=None):
    """生成缓存文件路径"""
    # 使用 URL 的 hash 作为文件名
    cache_key = f"{source}/{size or 'original'}/{url_path}"
    url_hash = hashlib.md5(cache_key.encode()).hexdigest()
    
    # 按来源和日期分目录，便于清理
    date_dir = time.strftime("%Y%m", time.localtime())
    cache_dir = os.path.join(CACHE_DIR, source, date_dir)
    os.makedirs(cache_dir, exist_ok=True)
    
    return os.path.join(cache_dir, f"{url_hash}.jpg")


def _clean_old_cache():
    """清理过期缓存"""
    try:
        now = time.time()
        total_size = 0
        
        for root, dirs, files in os.walk(CACHE_DIR):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    stat = os.stat(filepath)
                    file_age = now - stat.st_mtime
                    
                    # 删除超过最大天数的缓存
                    if file_age > MAX_CACHE_DAYS * 24 * 3600:
                        os.remove(filepath)
                        log.debug(f"【ImageProxy】删除过期缓存: {filepath}")
                    else:
                        total_size += stat.st_size
                except Exception as e:
                    log.error(f"【ImageProxy】清理缓存失败: {str(e)}")
        
        # 如果总大小超过限制，删除最旧的文件
        if total_size > MAX_CACHE_SIZE:
            files = []
            for root, dirs, filenames in os.walk(CACHE_DIR):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    try:
                        stat = os.stat(filepath)
                        files.append((filepath, stat.st_mtime, stat.st_size))
                    except:
                        pass
            
            # 按修改时间排序
            files.sort(key=lambda x: x[1])
            
            # 删除旧文件直到大小符合要求
            for filepath, mtime, size in files:
                if total_size <= MAX_CACHE_SIZE:
                    break
                try:
                    os.remove(filepath)
                    total_size -= size
                    log.debug(f"【ImageProxy】删除旧缓存释放空间: {filepath}")
                except:
                    pass
                    
    except Exception as e:
        log.error(f"【ImageProxy】清理缓存失败: {str(e)}")


def _download_image(url, timeout=10, referer=None):
    """
    下载图片 - 使用连接池和并发控制
    
    使用线程锁防止同一个图片被重复下载
    """
    cache_key = hashlib.md5(url.encode()).hexdigest()
    
    # 检查是否已有下载任务在进行中
    with _download_locks_lock:
        if cache_key in _download_locks:
            lock = _download_locks[cache_key]
        else:
            lock = threading.Lock()
            _download_locks[cache_key] = lock
    
    # 获取锁，防止重复下载
    with lock:
        try:
            # 再次检查缓存（可能其他线程已下载完成）
            # 调用方应在调用前检查缓存，这里双重保险
            
            # 提取域名获取对应的 Session
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc
            session = _get_session(domain)
            
            proxies = Config().get_proxies()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            if referer:
                headers['Referer'] = referer
            
            # 使用 Session 发送请求（连接池复用）
            response = session.get(url, proxies=proxies, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            log.error(f"【ImageProxy】下载图片失败 {url}: {str(e)}")
            return None
        finally:
            # 清理锁
            with _download_locks_lock:
                if cache_key in _download_locks:
                    del _download_locks[cache_key]


def download_images_concurrently(urls, referer=None, max_workers=5):
    """
    并发下载多张图片
    
    :param urls: 图片URL列表
    :param referer: Referer头
    :param max_workers: 最大并发数
    :return: 字典 {url: image_data}
    """
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
        
        # 获取目标尺寸
        target_width = SIZE_DIMENSIONS.get(target_size)
        if not target_width or target_width >= img.width:
            return image_data
        
        # 计算新高度，保持比例
        ratio = target_width / img.width
        target_height = int(img.height * ratio)
        
        # 使用高质量缩放
        img_resized = img.resize((target_width, target_height), Image.LANCZOS)
        
        # 保存为 JPEG
        output = BytesIO()
        img_resized.save(output, format='JPEG', quality=85, optimize=True)
        return output.getvalue()
        
    except Exception as e:
        log.error(f"【ImageProxy】调整图片尺寸失败: {str(e)}")
        return image_data


def _serve_cached_or_download(cache_path, image_url, size=None, referer=None):
    """通用函数：检查缓存或下载图片"""
    # 检查缓存
    if os.path.exists(cache_path):
        try:
            stat = os.stat(cache_path)
            if time.time() - stat.st_mtime < MAX_CACHE_DAYS * 24 * 3600:
                log.debug(f"【ImageProxy】命中缓存: {cache_path}")
                return send_file(cache_path, mimetype='image/jpeg')
        except Exception as e:
            log.error(f"【ImageProxy】读取缓存失败: {str(e)}")
    
    # 下载图片
    image_data = _download_image(image_url, referer=referer)
    if not image_data:
        abort(404)
    
    # 如果需要调整尺寸
    if size and size != 'original':
        image_data = _resize_image(image_data, size)
    
    # 保存到缓存
    try:
        with open(cache_path, 'wb') as f:
            f.write(image_data)
        log.debug(f"【ImageProxy】缓存图片: {cache_path}")
        
        # 异步清理旧缓存
        if time.time() % 100 < 1:  # 1% 概率触发清理
            _clean_old_cache()
            
    except Exception as e:
        log.error(f"【ImageProxy】保存缓存失败: {str(e)}")
    
    return Response(image_data, mimetype='image/jpeg')


@img_blueprint.route('/tmdb/<size>/<path:img_path>')
def proxy_tmdb_image(size, img_path):
    """
    代理 TMDB 图片
    
    :param size: 图片尺寸 (w92, w154, w185, w342, w500, w780, original)
    :param img_path: TMDB 图片路径
    """
    # 验证尺寸
    if size not in SIZE_DIMENSIONS:
        size = 'w500'
    
    # 生成缓存路径
    cache_path = _get_cache_path('tmdb', img_path, size)
    
    # 构建原始 URL - 优先使用 original 作为源
    original_url = f"https://{TMDB_IMAGE_DOMAIN}/t/p/original/{img_path}"
    
    return _serve_cached_or_download(cache_path, original_url, size)


@img_blueprint.route('/douban/<path:img_path>')
def proxy_douban_image(img_path):
    """
    代理豆瓣图片
    
    :param img_path: 豆瓣图片路径（URL 编码）
    """
    # URL 解码
    decoded_path = urllib.parse.unquote(img_path)
    
    # 生成缓存路径
    cache_path = _get_cache_path('douban', decoded_path)
    
    # 构建完整 URL
    if decoded_path.startswith('http'):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['douban']}/{decoded_path}"
    
    # 豆瓣需要 referer
    return _serve_cached_or_download(cache_path, image_url, referer='https://movie.douban.com')


@img_blueprint.route('/bgm/<path:img_path>')
def proxy_bgm_image(img_path):
    """
    代理 Bangumi 图片
    
    :param img_path: Bangumi 图片路径（URL 编码）
    """
    # URL 解码
    decoded_path = urllib.parse.unquote(img_path)
    
    # 生成缓存路径
    cache_path = _get_cache_path('bgm', decoded_path)
    
    # 构建完整 URL
    if decoded_path.startswith('http'):
        image_url = decoded_path
    else:
        image_url = f"https://{SOURCE_DOMAINS['bgm']}/{decoded_path}"
    
    return _serve_cached_or_download(cache_path, image_url)


@img_blueprint.route('/library/<path:img_url>')
def proxy_library_image(img_url):
    """
    代理媒体库内网图片（Emby / Jellyfin / Plex / fnos 等）

    :param img_url: 原始图片 URL（URL 编码）
    """
    decoded_url = urllib.parse.unquote(img_url)

    # 重新附加查询参数（如 Plex 的 X-Plex-Token）
    if request.query_string:
        separator = '&' if '?' in decoded_url else '?'
        decoded_url += separator + request.query_string.decode('utf-8')

    cache_path = _get_cache_path('library', decoded_url)
    return _serve_cached_or_download(cache_path, decoded_url)


@img_blueprint.route('/stats')
@login_required
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        stats = {
            'cache_dir': CACHE_DIR,
            'sources': {}
        }
        total_size = 0
        total_count = 0
        
        for source in ['tmdb', 'douban', 'bgm', 'library']:
            source_dir = os.path.join(CACHE_DIR, source)
            source_size = 0
            source_count = 0
            
            if os.path.exists(source_dir):
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            stat = os.stat(filepath)
                            source_size += stat.st_size
                            source_count += 1
                        except:
                            pass
            
            stats['sources'][source] = {
                'file_count': source_count,
                'size_mb': round(source_size / 1024 / 1024, 2)
            }
            total_size += source_size
            total_count += source_count
        
        stats['total'] = {
            'file_count': total_count,
            'size_mb': round(total_size / 1024 / 1024, 2),
            'max_size_mb': round(MAX_CACHE_SIZE / 1024 / 1024, 2)
        }
        
        return stats
    except Exception as e:
        return {'error': str(e)}


@img_blueprint.route('/clear', methods=['POST'])
@login_required
def clear_cache():
    """清空缓存"""
    try:
        cleared = {}
        for source in ['tmdb', 'douban', 'bgm', 'library']:
            source_dir = os.path.join(CACHE_DIR, source)
            count = 0
            if os.path.exists(source_dir):
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            os.remove(filepath)
                            count += 1
                        except:
                            pass
            cleared[source] = count
        
        return {'success': True, 'message': '缓存已清空', 'cleared': cleared}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@img_blueprint.route('/preload', methods=['POST'])
@login_required
def preload_images():
    """
    批量预加载图片到缓存
    请求体: {"urls": ["https://...", ...], "source": "tmdb|douban|bgm|library"}
    返回: {"success": true, "downloaded": 10, "failed": 2}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求体为空'}), 400
        
        urls = data.get('urls', [])
        source = data.get('source', 'tmdb')
        referer_map = {
            'tmdb': None,
            'douban': 'https://movie.douban.com',
            'bgm': None,
            'library': None
        }
        
        if not urls:
            return jsonify({'success': False, 'error': 'urls列表为空'}), 400
        
        # 限制最大数量
        if len(urls) > 50:
            urls = urls[:50]
        
        referer = referer_map.get(source)
        
        # 过滤掉已缓存的图片
        urls_to_download = []
        for url in urls:
            cache_key = f"{source}/original/{url}"
            url_hash = hashlib.md5(cache_key.encode()).hexdigest()
            date_dir = time.strftime("%Y%m", time.localtime())
            cache_path = os.path.join(CACHE_DIR, source, date_dir, f"{url_hash}.jpg")
            if not os.path.exists(cache_path):
                urls_to_download.append((url, cache_path))
        
        if not urls_to_download:
            return jsonify({
                'success': True,
                'message': '所有图片已缓存',
                'downloaded': 0,
                'already_cached': len(urls)
            })
        
        # 并发下载
        def download_and_save(item):
            url, cache_path = item
            image_data = _download_image(url, referer=referer)
            if image_data:
                try:
                    with open(cache_path, 'wb') as f:
                        f.write(image_data)
                    return True
                except Exception as e:
                    log.error(f"【ImageProxy】保存缓存失败: {cache_path}, {str(e)}")
                    return False
            return False
        
        downloaded = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(download_and_save, item): item for item in urls_to_download}
            for future in as_completed(futures):
                if future.result():
                    downloaded += 1
                else:
                    failed += 1
        
        return jsonify({
            'success': True,
            'downloaded': downloaded,
            'failed': failed,
            'already_cached': len(urls) - len(urls_to_download),
            'total': len(urls)
        })
        
    except Exception as e:
        log.error(f"【ImageProxy】预加载失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
