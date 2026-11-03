"""Torznab/JSON 索引器共享基类，统一搜索、列表、分页与统计。"""

from __future__ import annotations

import datetime
import threading
import time
from abc import abstractmethod
from typing import Any

import log
from app.domain.enums import ProgressKey, SearchType
from app.indexer.client.base import IndexerClientBase
from app.utils import StringUtils


class TorznabIndexerClient(IndexerClientBase):
    """Jackett/Prowlarr 等 Torznab 兼容客户端的公共实现。"""

    indexer_cache_ttl = 60.0

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.last_error = ""
        self._indexer_cache: list[Any] = []
        self._indexer_cache_at = 0.0
        self._cache_lock = threading.Lock()

    def get_indexers(self, check=True, indexer_id=None, public=True) -> Any:
        with self._cache_lock:
            now = time.monotonic()
            if not self._indexer_cache or now - self._indexer_cache_at > self.indexer_cache_ttl:
                try:
                    self._indexer_cache = list(self._fetch_indexers())
                    self._indexer_cache_at = now
                    self.last_error = ""
                except Exception as exc:  # noqa: BLE001
                    self.last_error = str(exc)
                    log.warn(f"[{self.index_type}]获取索引器失败: {exc}")
                    self._indexer_cache = []
            indexers = list(self._indexer_cache)
        if indexer_id is not None:
            return next(
                (
                    indexer
                    for indexer in indexers
                    if str(getattr(indexer, "id", "")) == str(indexer_id) or getattr(indexer, "name", "") == indexer_id
                ),
                None,
            )
        return indexers

    def get_status(self) -> bool:
        return bool(self.api_key and self.host and self.get_indexers())

    @abstractmethod
    def _fetch_indexers(self) -> list[Any]:
        """从远端获取索引器列表，结果由基类缓存。"""

    @abstractmethod
    def _search_items(self, indexer: Any, keyword: str) -> list[dict[str, Any]]:
        """返回某站点的全部搜索结果。"""

    @abstractmethod
    def _list_items(self, indexer: Any, keyword: str | None, offset: int, limit: int) -> list[dict[str, Any]]:
        """返回指定分页的列表结果。"""

    def search(self, order_seq, indexer, key_word, filter_args: dict, match_media, in_from: SearchType):
        if not indexer or not key_word:
            return []
        filter_args = filter_args or {}
        if filter_args.get("site") and indexer.name not in filter_args.get("site"):
            return []

        progress_key = ProgressKey.SubscribeSearch if in_from == SearchType.SUBSCRIBE else ProgressKey.Search
        start = datetime.datetime.now()
        log.info(f"[{self.index_type}]开始搜索Indexer：{indexer.name} ...")
        self.last_error = ""
        try:
            result_array = self._search_items(indexer, str(key_word))
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            result_array = []
            log.warn(f"[{self.index_type}]{indexer.name} 搜索失败: {exc}")
        self._record_stat(indexer.name, start, bool(self.last_error))
        self._update_progress(progress_key, indexer.name, key_word, len(result_array))
        return self._inject_meta(result_array, indexer, order_seq)

    def list(self, index_id, page=0, page_size=100, keyword=None):
        if not index_id:
            return None
        indexer = self.get_indexers(check=False, indexer_id=index_id)
        if not indexer:
            self.last_error = f"索引器不存在: {index_id}"
            return None
        page = max(0, int(page))
        page_size = max(1, min(1000, int(page_size)))
        offset = page * page_size
        start = datetime.datetime.now()
        self.last_error = ""
        try:
            items = self._list_items(indexer, keyword, offset, page_size)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            items = []
            log.warn(f"[{self.index_type}]{indexer.name} 列表失败: {exc}")
        self._record_stat(indexer.name, start, bool(self.last_error))
        return self._inject_meta(items, indexer, 0)

    def _record_stat(self, indexer_name: str, start: datetime.datetime, failed: bool) -> None:
        if not self.download_repo:
            return
        try:
            seconds = round((datetime.datetime.now() - start).total_seconds(), 1)
            self.download_repo.insert_indexer_statistics(
                indexer=indexer_name,
                itype=self.client_type or self.client_id,
                seconds=int(seconds),
                result="N" if failed else "Y",
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[{self.index_type}]写入统计失败: {exc!s}")

    def _update_progress(self, progress_key, indexer_name: str, keyword: str, count: int) -> None:
        if not self.progress:
            return
        if count == 0:
            self.progress.update(ptype=progress_key, text=f"{indexer_name} 关键词 {keyword} 未搜索到数据")
        else:
            self.progress.update(ptype=progress_key, text=f"{indexer_name} 关键词 {keyword} 返回 {count} 条数据")

    def _inject_meta(self, items: list[dict[str, Any]], indexer: Any, order_seq: int) -> list[dict[str, Any]]:
        for item in items:
            item["_indexer_name"] = indexer.name
            item["_indexer_order"] = order_seq
            item["_indexer_public"] = getattr(indexer, "public", False)
            item["_indexer_source"] = self.client_type or self.client_id
        return items

    @staticmethod
    def _search_text(keyword: str) -> str:
        return str(StringUtils.handler_special_chars(text=keyword, replace_word=" ", allow_space=True) or "")
