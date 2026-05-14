"""
索引器客户端抽象基类

职责：定义所有索引器客户端必须实现的接口协议，
并提供基于 Torznab XML 的通用搜索默认实现。
所有业务逻辑（过滤、识别）已迁移到 app.indexer.core。
"""

import datetime
import xml.dom.minidom
from abc import ABCMeta, abstractmethod

import log
from app.helper import ProgressHelper
from app.utils import DomUtils, ExceptionUtils, RequestUtils, StringUtils
from app.utils.types import ProgressKey, SearchType


class _IIndexClient(metaclass=ABCMeta):
    """
    索引器客户端抽象基类

    子类必须实现：
    - match()          : 判断是否匹配给定类型
    - get_status()     : 检查连通性
    - get_type()       : 获取索引器类型
    - get_client_id()  : 获取索引器ID
    - get_indexers()   : 获取可用站点列表

    search() 提供默认的 Torznab XML 解析实现，子类可重写。
    """

    client_id = ""
    client_type = ""
    client_name = "Indexer"
    index_type = ""
    api_key = ""
    host = ""
    progress = None

    def __init__(self):
        self.progress = ProgressHelper()

    @classmethod
    @abstractmethod
    def match(cls, ctype):
        """匹配实例"""

    @abstractmethod
    def get_status(self):
        """检查连通性"""

    @abstractmethod
    def get_type(self):
        """获取类型"""

    @abstractmethod
    def get_client_id(self):
        """获取索引器id"""

    @abstractmethod
    def get_indexers(self, check=True, indexer_id=None, public=True):
        """获取索引站点列表"""

    def search(self, order_seq, indexer, key_word, filter_args: dict, match_media, in_from: SearchType):
        """
        默认搜索实现：基于 Torznab XML 协议

        子类可重写此方法来提供自定义搜索逻辑。
        返回原始搜索结果（dict 列表），不执行过滤或识别。
        """
        if not indexer or not key_word:
            return []
        if filter_args is None:
            filter_args = {}
        if filter_args.get("site") and indexer.name not in filter_args.get("site"):
            return []

        progress_key = ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search
        start_time = datetime.datetime.now()
        log.info(f"【{self.index_type}】开始搜索Indexer：{indexer.name} ...")

        search_word = StringUtils.handler_special_chars(text=key_word, replace_word=" ", allow_space=True)
        api_url = f"{indexer.domain}?apikey={self.api_key}&t=search&q={search_word}"
        result_array = self.__parse_torznabxml(api_url)

        _ = (datetime.datetime.now() - start_time).seconds
        if len(result_array) == 0:
            log.warn(f"【{self.index_type}】{indexer.name} 关键词 {key_word} 未搜索到数据")
            if self.progress:
                self.progress.update(ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 未搜索到数据")
            return []
        else:
            log.warn(f"【{self.index_type}】{indexer.name} 关键词 {key_word} 返回数据：{len(result_array)}")
            if self.progress:
                self.progress.update(
                    ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 返回 {len(result_array)} 条数据"
                )

        # 注入站点元信息
        for item in result_array:
            item["_indexer_name"] = indexer.name
            item["_indexer_order"] = order_seq
            item["_indexer_public"] = getattr(indexer, "public", False)

        return result_array

    @staticmethod
    def __parse_torznabxml(url):
        """解析 Torznab XML"""
        ret_array = []
        if not url:
            return []
        try:
            ret = RequestUtils().get_res(url)
            if not ret:
                return []
            xml_doc = xml.dom.minidom.parseString(ret.text)
            items = xml_doc.getElementsByTagName("item")
            for item in items:
                try:
                    title = DomUtils.tag_value(item, "title", default="")
                    enclosure = DomUtils.tag_value(item, "enclosure", "url", default="")
                    if not enclosure:
                        enclosure = DomUtils.tag_value(item, "link", default="")
                    size = DomUtils.tag_value(item, "size", default=0)
                    description = DomUtils.tag_value(item, "description", default="")
                    seeders = 0
                    peers = 0
                    for node in item.getElementsByTagName("torznab:attr"):
                        if node.getAttribute("name") == "seeders":
                            seeders = node.getAttribute("value")
                        if node.getAttribute("name") == "peers":
                            peers = node.getAttribute("value")
                    ret_array.append(
                        {
                            "title": title,
                            "enclosure": enclosure,
                            "description": description,
                            "size": size,
                            "seeders": seeders,
                            "peers": peers,
                        }
                    )
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    continue
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
        return ret_array
