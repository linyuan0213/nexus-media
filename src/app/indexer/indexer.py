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
from app.core.constants import site_priority_order
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
    PriorityProvider,
    SiteIndexerProvider,
    get_global_registry,
    load_providers,
)
from app.indexer.contract.site_catalog import external_indexer_sites
from app.indexer.core.pipeline import SearchPipeline
from app.indexer.registry import get_all_clients, get_client_class
from app.infrastructure.progress import ProgressTracker
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.utils import ExceptionUtils, StringUtils

if TYPE_CHECKING:
    from app.services.site_grant_service import SiteGrantService


def resolve_indexer_priority(
    indexer: object,
    configured: int | str | None,
    site_priorities: dict[str, int],
) -> int:
    """解析索引器优先级：索引器显式配置 > 站点管理优先级 > 公共兜底.

    `site_priorities` 来自 CONFIG_SITE.PRI（用户在站点管理里设置的顺序），
    必须优先于 public 索引器的固定兜底值，否则公共站会与主站并列。
    """
    if configured is not None:
        return int(configured)
    name = str(getattr(indexer, "name", "") or "")
    if name in site_priorities:
        return int(site_priorities[name])
    if getattr(indexer, "public", False):
        return 100
    return int(getattr(indexer, "pri", 100) or 100)


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
        priority_map = self._site_config_repo.get_priority_map()
        site_priorities: dict[str, int] = {}
        for site in self._site_cache.get_sites(public=True):
            site_name = str(site.get("name") or "")
            site_pri = site.get("pri")
            if site_name and site_pri is not None:
                site_priorities[site_name] = int(str(site_pri))
        for client in self._clients.values():
            source = client.get_client_id()
            for indexer in self._filter_indexers(client, check=True, filter_args=filter_args):
                configured = priority_map.get(f"{source}:{indexer.name}")
                pri = resolve_indexer_priority(indexer, configured, site_priorities)
                provider = SiteIndexerProvider(client, indexer, site_priority_order(pri))
                registry.register(
                    PriorityProvider(provider, {indexer.name: pri}, default=pri),
                    replace=True,
                )
        self._ensure_external_providers()
        site_filter = (filter_args or {}).get("site")
        external_sites: dict[str, set[str]] = {}
        for site in external_indexer_sites():
            external_sites.setdefault(str(site.get("source") or ""), set()).add(str(site.get("name") or ""))
        site_filter_set = set(site_filter) if site_filter is not None else None
        user_id = filter_args.get("user_id") if filter_args else None
        visible = None
        grant_service = self.site_grant_service
        if user_id and grant_service is not None:
            visible = grant_service.get_visible_sites_by_id(user_id)
        for provider in self._external_registry.list():
            provider_sites = external_sites.get(provider.provider_id, set())
            allowed_sites = provider_sites
            if visible is not None and grant_service is not None:
                allowed_sites = set()
                for site in provider_sites:
                    if grant_service.is_site_allowed(visible, site, provider.provider_id, usage="search"):
                        allowed_sites.add(site)
                # 外部 provider 一次搜索会覆盖其全部站点；部分授权时整体跳过，避免越权站点。
                if not allowed_sites or allowed_sites != provider_sites:
                    continue
            requested = site_filter_set if site_filter_set is not None else allowed_sites
            if not (requested & allowed_sites):
                continue
            prefix = f"{provider.provider_id}:"
            priorities = {key[len(prefix) :]: value for key, value in priority_map.items() if key.startswith(prefix)}
            registry.register(PriorityProvider(provider, priorities), replace=True)
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
        progress = filter_args.get("progress_child") or self.progress
        registry = self.build_search_registry(filter_args)
        if not registry.list():
            log.error("没有可用索引器站点，无法搜索！")
            return []

        sites = site_filter or ()
        if isinstance(sites, str):
            sites = (sites,)
        start_time = datetime.datetime.now()

        def set_progress(pct: float, text: str) -> None:
            progress.update_max(ptype=progress_key, value=int(pct), text=text)

        site_statuses: list[dict] = []

        def on_provider_progress(completed, total, provider, count, error):
            name = getattr(provider, "provider_id", "provider") if provider else "provider"
            suffix = f"，返回 {count} 条" if count else (f"，失败：{error}" if error else "")
            set_progress(
                5 + (50 * completed / total if total else 0),
                f"索引器搜索 {completed}/{total}（{name}）{suffix}",
            )
            if provider is not None:
                site_statuses.append(
                    {
                        "name": name,
                        "status": "error" if error else "ok",
                        "count": count,
                        "error": error or "",
                    }
                )
                detail = progress.get_process(progress_key)
                if detail is not None:
                    detail["sites"] = list(site_statuses)

        set_progress(2, f"准备索引器，站点/提供方 {len(registry.list())} 个 ...")
        page = IndexerGateway(
            registry, max_workers=min(24, max(1, len(registry.list()))), on_progress=on_provider_progress
        ).search(
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
        set_progress(58, f"聚合 {len(raw_results)} 条结果，开始识别过滤 ...")

        pipeline_result = self._pipeline.process(
            all_results=self._dedup(raw_results),
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from,
            progress_key=progress_key,
            search_name=key_word,
            progress=progress,
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
        progress.update(
            ptype=progress_key,
            text=(
                f"搜索关键词 {key_word} 完成，有效资源数：{len(pipeline_result.results)}，"
                f"总耗时 {(end_time - start_time).seconds} 秒{failed_summary}"
            ),
        )
        return pipeline_result.results

    @staticmethod
    def _provider_to_raw(item: IndexerItem) -> dict:
        extra = item.extra
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
            "_indexer_source": str(extra.get("source") or item.provider_id.split(":", 1)[0]),
            "_indexer_public": bool(extra.get("public", False)),
            "_external_indexer": bool(extra.get("external")),
            "_indexer_order": site_priority_order(item.priority),
            "uploadvolumefactor": extra.get("uploadvolumefactor"),
            "downloadvolumefactor": extra.get("downloadvolumefactor"),
            "labels": extra.get("labels"),
            "imdbid": extra.get("imdbid"),
        }

    @staticmethod
    def _dedup(results: list[dict]) -> list[dict]:
        """按 (title, size) 去重；builtin 来源优先，同来源 order_seq 大者（pri 小=主站）优先"""
        ordered = sorted(
            results,
            key=lambda r: (
                -int(r.get("_indexer_order", 0) or 0),
                0 if str(r.get("_indexer_source") or "") == "builtin" else 1,
            ),
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
