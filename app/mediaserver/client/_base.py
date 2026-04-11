import json
from abc import ABCMeta, abstractmethod
from urllib.parse import quote

from config import Config


class _IMediaClient(metaclass=ABCMeta):

    # 媒体服务器ID
    client_id = ""
    # 媒体服务器类型
    client_type = ""
    # 媒体服务器名称
    client_name = ""

    @classmethod
    def get_db_config(cls, name):
        """从数据库获取配置，兼容旧配置文件"""
        from app.db.repositories import ConfigRepository
        repo = ConfigRepository()
        item = repo.get_media_server_by_name(name)
        if item and item.CONFIG:
            try:
                return json.loads(item.CONFIG)
            except Exception:
                pass
        return Config().get_config(name)

    @abstractmethod
    def match(self, ctype):
        """
        匹配实例
        """
        pass

    @abstractmethod
    def get_type(self):
        """
        获取媒体服务器类型
        """
        pass

    @abstractmethod
    def get_status(self):
        """
        检查连通性
        """
        pass

    @abstractmethod
    def get_user_count(self):
        """
        获得用户数量
        """
        pass

    @abstractmethod
    def get_activity_log(self, num):
        """
        获取Emby活动记录
        """
        pass

    @abstractmethod
    def get_medias_count(self):
        """
        获得电影、电视剧、动漫媒体数量
        :return: MovieCount SeriesCount SongCount
        """
        pass

    @abstractmethod
    def get_movies(self, title, year):
        """
        根据标题和年份，检查电影是否在存在，存在则返回列表
        :param title: 标题
        :param year: 年份，可以为空，为空时不按年份过滤
        :return: 含title、year属性的字典列表
        """
        pass

    @abstractmethod
    def get_tv_episodes(self, item_id=None, title=None, year=None, tmdbid=None, season=None):
        """
        根据标题、年份、季查询电视剧所有集信息
        :param item_id: 服务器中的ID
        :param title: 标题
        :param year: 年份，可以为空，为空时不按年份过滤
        :param tmdbid: TMDBID
        :param season: 季号，数字
        :return: 所有集的列表
        """
        pass

    @abstractmethod
    def get_no_exists_episodes(self, meta_info, season, total_num):
        """
        根据标题、年份、季、总集数，查询缺少哪几集
        :param meta_info: 已识别的需要查询的媒体信息
        :param season: 季号，数字
        :param total_num: 该季的总集数
        :return: 该季不存在的集号列表
        """
        pass

    @abstractmethod
    def get_remote_image_by_id(self, item_id, image_type):
        """
        根据ItemId查询远程图片地址
        :param item_id: 在服务器中的ID
        :param image_type: 图片的类弄地，poster或者backdrop等
        :return: 图片对应在TMDB中的URL
        """
        pass

    @abstractmethod
    def get_local_image_by_id(self, item_id):
        """
        根据ItemId查询本地图片地址，需要有外网地址
        :param item_id: 在服务器中的ID
        :return: 图片对应在TMDB中的URL
        """
        pass

    @abstractmethod
    def refresh_root_library(self):
        """
        刷新整个媒体库
        """
        pass

    @abstractmethod
    def refresh_library_by_items(self, items):
        """
        按类型、名称、年份来刷新媒体库
        :param items: 已识别的需要刷新媒体库的媒体信息列表
        """
        pass

    @abstractmethod
    def get_libraries(self):
        """
        获取媒体服务器所有媒体库列表
        """
        pass

    @abstractmethod
    def get_items(self, parent):
        """
        获取媒体库中的所有媒体
        :param parent: 上一级的ID
        """
        pass

    @abstractmethod
    def get_play_url(self, item_id):
        """
        获取媒体库中的所有媒体
        :param item_id: 媒体的的ID
        """
        pass

    @abstractmethod
    def get_playing_sessions(self):
        """
        获取正在播放的会话
        """
        pass

    @abstractmethod
    def get_webhook_message(self, message):
        """
        解析Webhook报文，获取消息内容结构
        """
        pass

    @staticmethod
    def get_nt_image_url(url, remote=False):
        """
        获取NT中转内网图片的地址
        优先使用本地文件缓存代理（/img/tmdb/, /img/douban/, /img/bgm/）
        对于其他图片统一使用本地文件缓存代理（/img/library/）
        当新代理不可用时回退到旧的 Redis 缓存代理（/img?url=）
        :param: url: 图片的URL
        :param: remote: 是否需要返回完整的URL
        """
        if not url:
            return ""
        
        # 检查是否启用了新的图片代理
        try:
            from config import Config
            if Config().get_image_proxy_enabled():
                # 处理 TMDB 图片
                if 'image.tmdb.org' in url:
                    # 提取路径部分
                    import re
                    match = re.search(r'/t/p/(\w+)(/.+)', url)
                    if match:
                        size = match.group(1)
                        path = match.group(2).lstrip('/')
                        proxy_url = f"/img/tmdb/{size}/{path}"
                        if remote:
                            domain = Config().get_domain()
                            if domain:
                                return f"{domain}{proxy_url}"
                        return proxy_url
                
                # 处理豆瓣图片
                if 'doubanio.com' in url or 'douban.com' in url:
                    import urllib.parse
                    encoded_path = urllib.parse.quote(url, safe='')
                    proxy_url = f"/img/douban/{encoded_path}"
                    if remote:
                        domain = Config().get_domain()
                        if domain:
                            return f"{domain}{proxy_url}"
                    return proxy_url
                
                # 处理 Bangumi 图片
                if 'lain.bgm.tv' in url:
                    import urllib.parse
                    encoded_path = urllib.parse.quote(url, safe='')
                    proxy_url = f"/img/bgm/{encoded_path}"
                    if remote:
                        domain = Config().get_domain()
                        if domain:
                            return f"{domain}{proxy_url}"
                    return proxy_url
                
                # 处理媒体库等其他图片，统一走本地文件缓存代理
                import urllib.parse
                encoded_path = urllib.parse.quote(url, safe='')
                proxy_url = f"/img/library/{encoded_path}"
                if remote:
                    domain = Config().get_domain()
                    if domain:
                        return f"{domain}{proxy_url}"
                return proxy_url
        except Exception as e:
            import log
            log.error(f"【get_nt_image_url】处理图片代理失败: {str(e)}")
        
        # 默认使用旧的 Redis 缓存代理
        if remote:
            domain = Config().get_domain()
            if domain:
                return f"{domain}/img?url={quote(url)}"
            else:
                return ""
        else:
            return f"img?url={quote(url)}"
