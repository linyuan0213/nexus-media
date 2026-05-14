"""
ConfigTools - 配置辅助纯函数
从 Config 类拆分出来，所有函数直接从 config 读取并返回结果
"""
from app.core.config import Config
from app.core.constants import DEFAULT_UA, TMDB_API_DOMAINS


def get_proxies():
    """获取代理配置"""
    return Config().get('app').get("proxies")


def get_ua():
    """获取 User-Agent"""
    return Config().get('app').get("user_agent") or DEFAULT_UA


def get_domain():
    """获取域名"""
    domain = (Config().get('app') or {}).get('domain')
    if domain and not domain.startswith('http'):
        domain = "http://" + domain
    if domain and str(domain).endswith("/"):
        domain = domain[:-1]
    return domain


def get_tmdbapi_url():
    """获取 TMDB API URL"""
    return f"https://{Config().get('app').get('tmdb_domain') or TMDB_API_DOMAINS[0]}/3"


def update_favtype(favtype):
    """更新收藏类型"""
    global RMT_FAVTYPE
    if favtype:
        RMT_FAVTYPE = favtype
