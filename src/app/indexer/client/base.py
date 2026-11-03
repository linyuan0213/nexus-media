"""索引器客户端基础类：配置、索引器描述和 Torznab XML 解析。"""

from __future__ import annotations

from typing import Any

import defusedxml.minidom  # type: ignore[import-untyped]

from app.db.repositories.download_repository import DownloadRepository
from app.indexer.schema import IndexerConfigSchema
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.exceptions import HttpClientError
from app.utils import DomUtils, ExceptionUtils


class IndexerClientBase:
    """内置/Jackett/Prowlarr 客户端的内部基础类，不承担搜索编排。"""

    client_id = ""
    client_type = ""
    client_name = "Indexer"
    config_schema: IndexerConfigSchema | None = None
    index_type = ""
    api_key = ""
    host = ""
    progress = None

    def __init__(self, progress=None, download_repo: DownloadRepository | None = None):
        self.progress = progress
        self.download_repo = download_repo

    @classmethod
    def match(cls, ctype) -> Any:
        raise NotImplementedError

    def get_status(self) -> Any:
        raise NotImplementedError

    def get_type(self) -> Any:
        return self.client_type

    def get_client_id(self) -> Any:
        return self.client_id

    def get_indexers(self, check=True, indexer_id=None, public=True) -> Any:
        raise NotImplementedError

    def search(self, order_seq, indexer, key_word, filter_args: dict, match_media, in_from) -> Any:
        raise NotImplementedError

    def list(self, index_id, page=0, page_size=100, keyword=None) -> list | None:
        return None

    def is_enabled(self) -> bool:
        return True

    @staticmethod
    def _parse_torznabxml(url: str) -> list[dict]:
        """解析 Torznab XML；HTTP 错误 / 超时 / 解析失败向上抛出。"""
        ret_array: list[dict] = []
        if not url:
            return ret_array
        ret = HttpClient().get(url)
        if not ret:
            raise HttpClientError("Torznab 请求无响应")
        xml_doc = defusedxml.minidom.parseString(ret.text)
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
        return ret_array
