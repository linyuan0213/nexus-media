import re
import xml.dom.minidom
from urllib.parse import urlsplit

from app.db.repositories.rss_torrent_repo_adapter import RssTorrentRepositoryAdapter
from app.utils import DomUtils, ExceptionUtils, RequestUtils, RssTitleUtils, StringUtils
from app.utils.config_tools import get_proxies, get_ua


class RssHelper:
    """RSS 解析助手"""

    def __init__(self):
        self._repo = RssTorrentRepositoryAdapter()

    @staticmethod
    def parse_rssxml(url, proxy=False):
        """
        解析RSS订阅URL，获取RSS中的种子信息
        :param url: RSS地址
        :param proxy: 是否使用代理
        :return: 种子信息列表，如为None代表Rss过期
        """
        _special_title_sites = {
            'pt.keepfrds.com': RssTitleUtils.keepfriends_title
        }

        _rss_expired_msg = [
            "RSS 链接已过期, 您需要获得一个新的!",
            "RSS Link has expired, You need to get a new one!"
        ]

        # 开始处理
        ret_array = []
        if not url:
            return []
        site_domain = StringUtils.get_url_domain(url)
        try:
            headers = {
                "Accept": "application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "User-Agent": get_ua()
            }
            ret = RequestUtils(headers=headers, proxies=get_proxies() if proxy else None).get_res(url)
            if not ret:
                return []
            ret.encoding = ret.apparent_encoding
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            return []
        if ret:
            ret_xml = ret.text
            try:
                # 解析XML
                dom_tree = xml.dom.minidom.parseString(ret_xml)
                rootNode = dom_tree.documentElement
                items = rootNode.getElementsByTagName("item")
                for item in items:
                    try:
                        # 标题
                        title = DomUtils.tag_value(item, "title", default="")
                        if not title:
                            continue
                        # 标题特殊处理
                        if site_domain and site_domain in _special_title_sites:
                            title = _special_title_sites.get(site_domain)(title)
                        # 描述
                        description = DomUtils.tag_value(item, "description", default="")
                        # 种子页面
                        link = DomUtils.tag_value(item, "link", default="")
                        # 种子链接
                        enclosure = DomUtils.tag_value(item, "enclosure", "url", default="")

                        if not enclosure and not link:
                            continue
                        # 部分RSS只有link没有enclosure
                        if not enclosure and link:
                            enclosure = link
                            link = None

                        # monika rss兼容
                        if enclosure and 'monikadesign' in enclosure:
                            tids = re.findall(r'(\d+)\.', enclosure)
                            if tids:
                                split_url = urlsplit(enclosure)
                                link = f"{split_url.scheme}://{split_url.netloc}/torrents/{tids[0]}"
                        # 大小
                        size = DomUtils.tag_value(item, "enclosure", "length", default=0)
                        if size == 0:
                            size = StringUtils.num_filesize(DomUtils.tag_value(item, "torrent:size", default=0))
                        if size and str(size).isdigit():
                            size = int(size)
                        else:
                            size = 0
                        # 发布日期
                        pubdate = DomUtils.tag_value(item, "pubDate", default="")
                        if pubdate:
                            # 转换为时间
                            pubdate = StringUtils.get_time_stamp(pubdate)
                        # 返回对象
                        tmp_dict = {'title': title,
                                    'enclosure': enclosure,
                                    'size': size,
                                    'description': description,
                                    'link': link,
                                    'pubdate': pubdate}
                        ret_array.append(tmp_dict)
                    except Exception as e1:
                        ExceptionUtils.exception_traceback(e1)
                        continue
            except Exception as e2:
                # RSS过期 观众RSS 链接已过期，您需要获得一个新的！  pthome RSS Link has expired, You need to get a new one!
                if ret_xml in _rss_expired_msg:
                    return None
                ExceptionUtils.exception_traceback(e2)
        return ret_array

    def insert_rss_torrents(self, media_info):
        """
        将RSS的记录插入数据库
        """
        enclosure = media_info.enclosure
        if enclosure and len(enclosure) > 8192:
            enclosure = enclosure[:8192]
        self._repo.insert(
            torrent_name=media_info.org_string,
            enclosure=enclosure,
            type_=media_info.type.value,
            title=media_info.title,
            year=media_info.year,
            season=media_info.get_season_string(),
            episode=media_info.get_episode_string(),
        )

    def is_rssd_by_enclosure(self, enclosure):
        """
        查询RSS是否处理过，根据下载链接
        """
        if not enclosure:
            return True
        return self._repo.is_exists_by_enclosure(enclosure)

    def is_rssd_by_simple(self, torrent_name, enclosure):
        """
        查询RSS是否处理过，根据名称或下载链接
        """
        if not torrent_name and not enclosure:
            return True
        return self._repo.is_exists_by_name(torrent_name, enclosure)

    def simple_insert_rss_torrents(self, title, enclosure):
        """
        将RSS的记录插入数据库（简式）
        """
        self._repo.simple_insert(title, enclosure)

    def simple_delete_rss_torrents(self, title, enclosure=None):
        """
        删除RSS的记录
        """
        self._repo.simple_delete(title, enclosure)

    def truncate_rss_history(self):
        """
        清空RSS历史记录
        """
        self._repo.truncate()
