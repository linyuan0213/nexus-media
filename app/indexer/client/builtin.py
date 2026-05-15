"""
内置索引器客户端

职责：管理用户配置的站点，调用各站点爬虫执行搜索，返回原始结果。
所有过滤和识别逻辑已迁移到 app.indexer.core.SearchPipeline。
"""

import copy
import datetime
import json as _json
from threading import Lock

import log
from app.core.system_config import SystemConfig
from app.db.repositories import DownloadRepository
from app.helper import IndexerConf, IndexerHelper, ProgressHelper
from app.helper.drissionpage_helper import DrissionPageHelper
from app.indexer.client._base import _IIndexClient
from app.sites import Sites
from app.sites.engine import SiteEngine
from app.sites.searcher_factory import create_searcher
from app.utils import StringUtils
from app.utils.config_tools import get_ua
from app.utils.types import IndexerType, ProgressKey, SearchType, SystemConfigKey
from config import Config

_STATS_LOCK = Lock()


class BuiltinIndexer(_IIndexClient):
    """
    内置索引器

    聚合所有用户配置的 PT/BT 站点，通过对应爬虫执行搜索。
    """

    client_id = "builtin"
    client_type = IndexerType.BUILTIN
    client_name = IndexerType.BUILTIN.value

    _client_config = {}
    _show_more_sites = False

    def __init__(self, config=None):
        self._client_config = config or {}
        self.init_config()

    def init_config(self):
        self.sites = Sites()
        self.progress = ProgressHelper()
        self.download_repo = DownloadRepository()
        self._show_more_sites = Config().get_config("laboratory").get("show_more_sites")

    @classmethod
    def match(cls, ctype):
        return ctype in [cls.client_id, cls.client_type, cls.client_name]

    def get_type(self):
        return self.client_type

    def get_client_id(self):
        return self.client_id

    def get_status(self):
        return True

    def get_indexers(self, check=True, indexer_id=None, public=True):
        """获取当前索引器的索引站点"""
        ret_indexers = []
        indexer_sites = SystemConfig().get(SystemConfigKey.UserIndexerSites) or []
        _indexer_domains = []

        chrome_ok = DrissionPageHelper().get_status()

        engine_sites = []
        for s in SiteEngine.get_instance().all_sites():
            if s.html:
                engine_sites.append(
                    {
                        "id": s.id,
                        "name": s.name,
                        "domain": s.domain,
                        "public": s.public,
                        "search": s.html.search,
                        "torrents": s.html.torrents,
                        "category": s.html.category,
                        "browse": s.html.browse,
                        "language": s.language,
                    }
                )
        IndexerHelper().set_indexers(engine_sites)

        for site in Sites().get_sites(public=True):
            url = site.get("signurl") or site.get("rssurl")
            cookie = site.get("cookie")
            headers = site.get("headers")
            is_public = site.get("public", False)

            if not url:
                continue
            if not is_public and not cookie and not headers:
                continue

            render = False if not chrome_ok else site.get("chrome")
            indexer = IndexerHelper().get_indexer(
                url=url,
                siteid=site.get("id"),
                cookie=cookie,
                ua=site.get("ua"),
                headers=site.get("headers"),
                name=site.get("name"),
                rule=site.get("rule"),
                pri=site.get("pri"),
                public=is_public,
                proxy=site.get("proxy"),
                render=render,
            )
            if indexer:
                if indexer_id and str(indexer.id) == str(indexer_id):
                    return indexer
                if check and (not indexer_sites or indexer.id not in indexer_sites):
                    continue
                if indexer.domain not in _indexer_domains:
                    _indexer_domains.append(indexer.domain)
                    indexer.name = site.get("name")
                    ret_indexers.append(indexer)

        if public and self._show_more_sites:
            for indexer in IndexerHelper().get_all_indexers():
                if not indexer.get("public"):
                    continue
                if indexer_id and indexer.get("id") == indexer_id:
                    return IndexerConf(datas=indexer)
                if check and (not indexer_sites or indexer.get("id") not in indexer_sites):
                    continue
                if indexer.get("domain") not in _indexer_domains:
                    _indexer_domains.append(indexer.get("domain"))
                    ret_indexers.append(IndexerConf(datas=indexer))

        return None if indexer_id else ret_indexers

    def search(self, order_seq, indexer, key_word, filter_args: dict, match_media, in_from: SearchType):
        """
        根据关键字搜索单个站点，返回原始结果（dict 列表）

        原始结果会自动注入站点元信息字段：
        - _indexer_name
        - _indexer_order
        - _indexer_public
        """
        progress_key = ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search
        if not indexer or not key_word:
            return []

        # 站点流控
        if self.sites.check_ratelimit(indexer.siteid):
            self.progress.update(ptype=progress_key, text=f"{indexer.name} 触发站点流控，跳过 ...")
            return []

        if filter_args is None:
            _filter_args = {}
        else:
            _filter_args = copy.deepcopy(filter_args)

        if _filter_args.get("site") and indexer.name not in _filter_args.get("site"):
            return []

        if not _filter_args.get("rule") and indexer.rule:
            _filter_args.update({"rule": indexer.rule})

        start_time = datetime.datetime.now()
        log.info(f"【{self.client_name}】开始搜索Indexer：{indexer.name} ...")

        search_word = StringUtils.handler_special_chars(text=key_word, replace_word=" ", allow_space=True)
        if indexer.language == "en" and StringUtils.is_chinese(search_word):
            log.warn(f"【{self.client_name}】{indexer.name} 无法使用中文名搜索")
            return []

        result_array = []
        error_flag = False
        mtype = match_media.type if (match_media and match_media.tmdb_info) else None
        try:
            error_flag, result_array = self.__search_via_engine(search_word=search_word, indexer=indexer, mtype=mtype)
        except Exception as err:
            error_flag = True
            print(str(err))

        seconds = round((datetime.datetime.now() - start_time).seconds, 1)

        # 索引统计
        with _STATS_LOCK:
            self.download_repo.insert_indexer_statistics(
                indexer=indexer.name, itype=self.client_id, seconds=seconds, result="N" if error_flag else "Y"
            )

        if len(result_array) == 0:
            log.warn(f"【{self.client_name}】{indexer.name} 关键词 {key_word} 未搜索到数据")
            self.progress.update(ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 未搜索到数据")
            return []
        else:
            log.warn(f"【{self.client_name}】{indexer.name} 关键词 {key_word} 返回数据：{len(result_array)}")
            self.progress.update(
                ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 返回 {len(result_array)} 条数据"
            )

        # 注入站点元信息
        for item in result_array:
            item["_indexer_name"] = indexer.name
            item["_indexer_order"] = order_seq
            item["_indexer_public"] = getattr(indexer, "public", False)

        return result_array

    def list(self, index_id, page=0, keyword=None):
        """
        根据站点ID搜索站点首页资源
        """
        if not index_id:
            return None
        indexer = self.get_indexers(indexer_id=index_id)
        if not indexer:
            log.warn(f"【BuiltinIndexer】list 未找到站点: {index_id}")
            return None

        log.warn(f"【BuiltinIndexer】list 找到站点: {indexer.name} (id={indexer.id}, domain={indexer.domain})")  # type: ignore[union-attr]
        start_time = datetime.datetime.now()

        error_flag, result_array = self.__search_via_engine(search_word=keyword, indexer=indexer, page=page)

        seconds = round((datetime.datetime.now() - start_time).seconds, 1)
        with _STATS_LOCK:
            self.download_repo.insert_indexer_statistics(
                indexer=indexer.name, itype=self.client_id, seconds=seconds, result="N" if error_flag else "Y"  # type: ignore[union-attr]
            )
        return result_array

    def __search_via_engine(self, search_word, indexer, mtype=None, page=0):
        engine = SiteEngine.get_instance()
        site_def = engine.get_by_id(str(indexer.id)) or engine.get_by_url(indexer.domain or "")
        if not site_def or not (site_def.api or site_def.html):
            return True, []
        user_config = self._build_user_config(indexer)
        searcher = create_searcher(indexer.domain, user_config)
        if not searcher:
            return True, []
        result_array = searcher.search(keyword=search_word, page=page, mtype=mtype)
        for item in result_array:
            if "indexer" not in item:
                item["indexer"] = indexer.id or indexer.siteid
        return False, result_array

    @staticmethod
    def _build_user_config(indexer):
        user_config = {
            "cookie": getattr(indexer, "cookie", "") or "",
            "ua": getattr(indexer, "ua", "") or get_ua(),
            "proxy": getattr(indexer, "proxy", False),
            "headers": getattr(indexer, "headers", {}) or {},
            "domain": getattr(indexer, "domain", "") or "",
        }
        if indexer.headers:
            try:
                h = _json.loads(indexer.headers) if isinstance(indexer.headers, str) else indexer.headers
                auth_val = (h or {}).get("Authorization") or (h or {}).get("authorization") or ""
                if auth_val.startswith("Bearer "):
                    user_config["api_key"] = auth_val[len("Bearer ") :]
            except Exception:
                pass
        return user_config
