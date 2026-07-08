"""
ConfigTools - 配置辅助纯函数
从 Config 类拆分出来，所有函数直接从 config 读取并返回结果
"""

from app.core.constants import DEFAULT_UA, TMDB_API_DOMAINS
from app.core.settings import settings


def get_proxies():
    """获取代理配置。

    统一规范化：只要 http/https 任一被配置（含 socks5://、socks5h:// 等），
    就把两个键都填成同一个地址，避免调用方只读 http 键时取不到 https 键里配置的代理。
    """
    proxies = settings.get("app").get("proxies")
    if isinstance(proxies, dict):
        proxy_url = proxies.get("http") or proxies.get("https")
        if proxy_url:
            return {"http": proxy_url, "https": proxy_url}
    return proxies


def get_ua():
    """获取 User-Agent"""
    return settings.get("app").get("user_agent") or DEFAULT_UA


def get_domain():
    """获取域名"""
    domain = (settings.get("app") or {}).get("domain")
    if domain and not domain.startswith("http"):
        domain = "http://" + domain
    if domain and str(domain).endswith("/"):
        domain = domain[:-1]
    return domain


def get_tmdbapi_url():
    """获取 TMDB API URL"""
    return f"https://{settings.get('app').get('tmdb_domain') or TMDB_API_DOMAINS[0]}/3"


def update_favtype(favtype):
    """更新收藏类型"""
    global RMT_FAVTYPE
    if favtype:
        RMT_FAVTYPE = favtype
