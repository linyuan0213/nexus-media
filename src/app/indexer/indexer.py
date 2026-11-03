"""
索引器管理模块

职责：
1. 管理所有索引器客户端（Builtin、Prowlarr、Jackett）
2. 并发调度多站点搜索
3. 收集所有原始结果后，统一调用 SearchPipeline 进行批量识别和过滤
"""

import datetime
import threading
from typing import TYPE_CHECKING

import log
from app.core.system_config import SystemConfig
from app.db.repositories.download_repository import DownloadRepository
from app.db.repositories.indexer_config_repo_adapter import IndexerConfigRepositoryAdapter
from app.db.repositories.indexer_site_config_repo_adapter import IndexerSiteConfigRepositoryAdapter
from app.domain.enums import ProgressKey, SearchType, SystemConfigKey
from app.indexer.client.base import IndexerClientBase
from app.indexer.configuration import IndexerHelper
from app.indexer.contract import (
    IndexerGateway,
    IndexerItem,
    IndexerProviderRegistry,
    IndexerQuery,
    SiteIndexerProvider,
    get_global_registry,
    load_providers,
)
from app.indexer.core.pipeline import SearchPipeline
from app.indexer.registry import get_all_clients, get_client_class
from app.infrastructure.progress import ProgressTracker
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.utils import ExceptionUtils, StringUtils

if TYPE_CHECKING:
    from app.services.site_grant_service import SiteGrantService


class Indexer:
    """索引器管理.

    搜索流程：
    1. 获取所有可用站点
    2. 并发搜索每个站点，收集原始结果（dict 列表）
    3. 将所有原始结果传入 SearchPipeline，统一批量识别和过滤
    4. 返回最终结果（meta_info 列表）
    """

    def __init__(
        self,
        search_pipeline: SearchPipeline,
        indexer_helper: IndexerHelper,
        site_cache: SiteCache,
        site_engine: SiteEngine,
        progress_helper: ProgressTracker | None = None,
        download_repo: DownloadRepository | None = None,
        system_config: SystemConfig | None = None,
        site_config_repo: IndexerSiteConfigRepositoryAdapter | None = None,
        idx_config_repo: IndexerConfigRepositoryAdapter | None = None,
    ):
        self.progress = progress_helper or ProgressTracker()
        self.download_repo = download_repo or DownloadRepository()
        self._pipeline = search_pipeline
        self._system_config = system_config or SystemConfig()
        self._indexer_helper = indexer_helper
        self._site_cache = site_cache
        self._site_engine = site_engine
        self._site_config_repo = site_config_repo or IndexerSiteConfigRepositoryAdapter()
        self._idx_config_repo = idx_config_repo or IndexerConfigRepositoryAdapter()
        # 站点授权服务（L3 资源访问控制），由 DI 装配后注入；None 表示不过滤
        self.site_grant_service: SiteGrantService | None = None
        self._client = None
        self._client_type = None
        self._clients: dict[str, IndexerClientBase] = {}
        self._clients_lock = threading.Lock()
        self._external_registry = IndexerProviderRegistry()

    def _ensure_client(self) -> None:
        """延迟加载 builtin 索引器客户端（兼容旧调用）"""
        if self._client is not None:
            return
        self._client = self.__get_client("builtin")
        self._client_type = self._client.get_type() if self._client else None

    def _ensure_clients(self) -> None:
        """延迟加载所有已配置的索引器客户端"""
        with self._clients_lock:
            if self._clients:
                return
            clients: dict[str, IndexerClientBase] = {}
            builtin_cfg = self._idx_config_repo.get_by_client_id("builtin")
            if builtin_cfg is None or builtin_cfg.enabled:
                builtin = self.__get_client("builtin")
                if builtin:
                    clients["builtin"] = builtin
            for ctype in ("jackett", "prowlarr"):
                entity = self._idx_config_repo.get_by_client_id(ctype)
                if entity is None or not entity.config:
                    continue
                cfg = entity.config
                if not cfg.get("host") or not cfg.get("api_key"):
                    continue
                if not entity.enabled:
                    continue
                client = self.__get_client(ctype, cfg)
                if client:
                    clients[ctype] = client
            self._clients = clients

    def __build_class(self, ctype, conf=None):
        ctype_str = ctype.value if hasattr(ctype, "value") else ctype
        for cls in get_all_clients():
            try:
                if cls.match(ctype_str):
                    if ctype_str == "builtin":
                        return cls(
                            conf,
                            indexer_helper=self._indexer_helper,
                            site_cache=self._site_cache,
                            site_engine=self._site_engine,
                            download_repo=self.download_repo,
                            idx_config_repo=self._idx_config_repo,
                        )
                    return cls(conf, download_repo=self.download_repo)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def __get_client(self, ctype, conf=None):
        return self.__build_class(ctype=ctype, conf=conf)

    def _refresh(self):
        """重置客户端缓存，下次访问时重新加载"""
        self._client = None
        self._client_type = None
        self._clients = {}

    def get_client(self):
        self._ensure_client()
        return self._client

    def get_client_type(self):
        self._ensure_client()
        return self._client_type

    def _ensure_external_providers(self) -> None:
        registry = IndexerProviderRegistry()
        for provider in get_global_registry().list():
            try:
                registry.register(provider, replace=True)
            except ValueError:
                pass
        config = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
        specs = config.get("providers") if isinstance(config, dict) else None
        if isinstance(specs, list):
            try:
                load_providers(registry, specs)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[Indexer]加载外部 provider 失败: {exc}")
        self._external_registry = registry

    def build_search_registry(self, filter_args: dict | None = None) -> IndexerProviderRegistry:
        """构建站点级 provider 注册表；旧客户端只作为 provider 内部实现。"""
        self._ensure_clients()
        registry = IndexerProviderRegistry()
        for client in self._clients.values():
            for indexer in self._filter_indexers(client, check=True, filter_args=filter_args):
                order_seq = 100 - int(getattr(indexer, "pri", 0))
                registry.register(SiteIndexerProvider(client, indexer, order_seq), replace=True)
        self._ensure_external_providers()
        for provider in self._external_registry.list():
            registry.register(provider, replace=True)
        return registry

    def get_indexers(self, check=False):
        """获取默认搜索索引器的站点列表（兼容旧调用）"""
        self._ensure_client()
        if not self._client:
            return []
        return self._client.get_indexers(check=check)

    def get_all_search_indexers(self, check=True):
        """获取所有已启用索引器的站点列表"""
        self._ensure_clients()
        indexers = []
        for client in self._clients.values():
            indexers.extend(self._filter_indexers(client, check=check))
        return indexers

    def get_indexers_with_source(self, check=True) -> list[dict]:
        """获取全部站点及其来源客户端（builtin/jackett/prowlarr），供站点授权展示与过滤"""
        self._ensure_clients()
        result = []
        for client in self._clients.values():
            source = client.get_client_id()
            for indexer in self._filter_indexers(client, check=check):
                result.append({"name": indexer.name, "source": source, "builtin": source == "builtin"})
        return result

    def _filter_indexers(self, client, check=True, filter_args=None):
        if not getattr(client, "is_enabled", lambda: True)():
            return []
        indexers = client.get_indexers(check=check)
        # 第三方索引器需要再用 DB 中的 enabled 状态过滤一次
        if client.get_client_id() != "builtin":
            enabled_names = set(self._site_config_repo.list_enabled_names(source=client.get_client_id()))
            indexers = [i for i in indexers if i.name in enabled_names]
        if filter_args and filter_args.get("site") is not None:
            # site 为 None → 不限制（WEB 搜索默认全部）
            # site 为空列表 → 订阅未配置站点，搜索零站点（不搜全站）
            site_filter = filter_args.get("site")
            indexers = [i for i in indexers if i.name in site_filter]
        # 站点授权过滤（L3）：filter_args 携带 user_id 且授权服务已注入时按白名单过滤
        user_id = filter_args.get("user_id") if filter_args else None
        if user_id and self.site_grant_service is not None:
            visible = self.site_grant_service.get_visible_sites_by_id(user_id)
            if visible is not None:
                source = client.get_client_id()
                before = len(indexers)
                indexers = [
                    i
                    for i in indexers
                    if self.site_grant_service.is_site_allowed(visible, i.name, source, usage="search")
                ]
                if before and not indexers:
                    log.warn(f"[Indexer]用户 {user_id} 未被授权任何可用搜索站点（原 {before} 个），请管理员授权")
        return indexers

    def get_user_indexer_dict(self):
        return [{"id": index.id, "name": index.name} for index in self.get_indexers(check=True)]

    def get_indexer_hash_dict(self):
        indexer_dict = {}
        for item in self.get_indexers() or []:
            indexer_dict[StringUtils.md5_hash(item.name)] = {
                "id": item.id,
                "name": item.name,
                "public": item.public,
                "builtin": item.builtin,
            }
        return indexer_dict

    def get_user_indexer_names(self):
        return [indexer.name for indexer in self.get_indexers(check=True)]

    def get_builtin_indexers(self, check=True, indexer_id=None):
        cls = get_client_class("builtin")
        if cls:
            return cls(
                indexer_helper=self._indexer_helper,
                site_cache=self._site_cache,
                site_engine=self._site_engine,
                download_repo=self.download_repo,
            ).get_indexers(check=check, indexer_id=indexer_id)
        return []

    def list_resources(self, index_id, page=0, page_size=100, keyword=None):
        if not index_id:
            return []
        builtin_cls = get_client_class("builtin")
        if builtin_cls:
            result = builtin_cls(
                indexer_helper=self._indexer_helper,
                site_cache=self._site_cache,
                site_engine=self._site_engine,
                download_repo=self.download_repo,
            ).list(index_id=index_id, page=page, page_size=page_size, keyword=keyword)
            if result is not None:
                return result
        site_config = self._site_config_repo.get_by_id(index_id)
        if site_config:
            if site_config.source == "builtin" and builtin_cls:
                result = builtin_cls(
                    indexer_helper=self._indexer_helper,
                    site_cache=self._site_cache,
                    site_engine=self._site_engine,
                    download_repo=self.download_repo,
                ).list(index_id=site_config.site_name, page=page, page_size=page_size, keyword=keyword)
                if result is not None:
                    return result
            elif site_config.source and site_config.source != "builtin":
                self._ensure_clients()
                idx_config = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
                cfg = idx_config.get(site_config.source, {})
                client = self._clients.get(site_config.source) or self.__get_client(site_config.source, cfg)
                if client:
                    result = client.list(
                        index_id=site_config.site_name, page=page, page_size=page_size, keyword=keyword
                    )
                    if result is not None:
                        return result
        return None

    def search_by_keyword(self, key_word, filter_args: dict, match_media=None, in_from: SearchType | None = None):
        """统一通过 IndexerGateway 搜索所有内置、第三方和插件索引器。"""
        if not key_word:
            return []
        filter_args = filter_args or {}
        site_filter = filter_args.get("site")
        if site_filter is not None and len(site_filter) == 0:
            log.info("站点列表为空，跳过搜索")
            return []
        progress_key = filter_args.get("progress_key") or (
            ProgressKey.SubscribeSearch if in_from == SearchType.SUBSCRIBE else ProgressKey.Search
        )
        registry = self.build_search_registry(filter_args)
        if not registry.list():
            log.error("没有可用索引器站点，无法搜索！")
            return []

        sites = site_filter or ()
        if isinstance(sites, str):
            sites = (sites,)
        start_time = datetime.datetime.now()
        self.progress.update(
            ptype=progress_key,
            text=f"开始通过 provider 搜索 {key_word}，站点数：{len(registry.list())} ...",
        )
        page = IndexerGateway(registry, max_workers=15).search(
            IndexerQuery(
                keyword=key_word,
                sites=tuple(sites),
                content_profile=filter_args.get("content_profile"),
                offset=0,
                limit=500,
            )
        )
        raw_results = [self._provider_to_raw(item) for item in page.items]
        if page.warnings:
            log.warn(f"[Indexer]provider 告警: {page.warnings}")

        pipeline_result = self._pipeline.process(
            all_results=self._dedup(raw_results),
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from,
            progress_key=progress_key,
            search_name=key_word,
        )
        end_time = datetime.datetime.now()
        failed_summary = ""
        if page.warnings:
            failed_summary = "；provider 告警：" + "；".join(page.warnings)
        log.info(
            f"搜索关键词 {key_word} 所有 provider 完成，"
            f"原始结果 {len(raw_results)} 条，有效资源数：{len(pipeline_result.results)}，"
            f"总耗时 {(end_time - start_time).seconds} 秒{failed_summary}"
        )
        self.progress.update(
            ptype=progress_key,
            text=(
                f"搜索关键词 {key_word} 完成，有效资源数：{len(pipeline_result.results)}，"
                f"总耗时 {(end_time - start_time).seconds} 秒{failed_summary}"
            ),
        )
        return pipeline_result.results

    @staticmethod
    def _provider_to_raw(item: IndexerItem) -> dict:
        return {
            "title": item.title,
            "enclosure": item.download_url or item.magnet or item.ed2k or "",
            "size": item.size_bytes or 0,
            "seeders": item.seeders or 0,
            "peers": item.peers or 0,
            "page_url": item.detail_url,
            "description": item.description,
            "_indexer_name": item.site or item.site_name,
            "_indexer_display_name": item.site_name or item.site,
            "_indexer_source": item.provider_id,
            "_external_indexer": bool(item.extra.get("external")),
            "_indexer_order": 0,
        }

    @staticmethod
    def _dedup(results: list[dict]) -> list[dict]:
        """按 (title, size) 去重；builtin 来源优先，同来源 order_seq 大者（pri 小=主站）优先"""
        ordered = sorted(
            results,
            key=lambda r: (0 if r.get("_indexer_source") == "builtin" else 1, -r.get("_indexer_order", 0)),
        )
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for r in ordered:
            key = (r.get("title", ""), r.get("size", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def get_indexer_statistics(self):
        """获取所有索引器统计信息"""
        self._ensure_clients()
        log.info(f"[Indexer]统计：已加载客户端 {list(self._clients.keys())}")
        stats = []
        for client in self._clients.values():
            rows = self.download_repo.get_indexer_statistics(client.get_client_id())
            for row in rows:
                stats.append(
                    {
                        "indexer": row[0],
                        "total": row[1],
                        "fail": row[2],
                        "success": row[3],
                        "avg": row[4] or 0,
                    }
                )
        return stats
