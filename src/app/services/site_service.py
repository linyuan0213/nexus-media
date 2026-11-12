from typing import Any

from app.db.repositories.indexer_config_repo_adapter import IndexerConfigRepositoryAdapter
from app.db.repositories.indexer_site_config_repo_adapter import IndexerSiteConfigRepositoryAdapter
from app.db.repositories.site_repository import SiteRepository
from app.domain.entities.site import SiteEntity
from app.domain.interfaces.site_repo import ISiteRepository
from app.schemas.site import (
    SiteActivityDTO,
    SiteAttrDTO,
    SiteDefinitionDTO,
    SiteDetailDTO,
    SiteHistoryDTO,
    SiteResourcesResultDTO,
    SiteSeedingDTO,
    SiteTestResultDTO,
    SiteUpdateResultDTO,
)
from app.services.indexer_service import IndexerService
from app.services.site_catalog_service import SiteCatalogService
from app.services.site_connectivity_service import SiteConnectivityService
from app.services.site_credential_service import SiteCredentialService
from app.services.site_crud_service import SiteCrudService
from app.services.site_resource_service import SiteResourceService
from app.services.site_statistics_service import SiteStatisticsService
from app.sites import SiteConf, SiteCookie
from app.sites.connectivity.site_favicon_service import SiteFaviconService
from app.sites.connectivity.site_resolver import SiteResolver
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.sites.userinfo.site_userinfo import SiteUserInfo


class SiteService:
    """站点业务服务：站点 CRUD、统计、连通性测试、资源列表"""

    def __init__(
        self,
        sites: SiteCache,
        site_user_info: SiteUserInfo,
        site_conf: SiteConf,
        indexer_service: IndexerService,
        site_repo: SiteRepository,
        site_favicon_service: SiteFaviconService,
        site_resolver: SiteResolver,
        site_cookie: SiteCookie,
        string_utils: Any,
        site_entity_repo: ISiteRepository,
        indexer_site_config_repo: IndexerSiteConfigRepositoryAdapter | None = None,
        site_engine: SiteEngine | None = None,
        idx_config_repo: IndexerConfigRepositoryAdapter | None = None,
    ):
        self._sites = sites
        self._site_user_info = site_user_info
        self._site_conf = site_conf
        self._site_cookie = site_cookie
        self._indexer_service = indexer_service
        self._string_utils = string_utils
        self._site_repo = site_repo
        self._site_entity_repo = site_entity_repo
        self._site_favicon_service = site_favicon_service
        self._site_resolver = site_resolver
        self._indexer_site_config_repo = indexer_site_config_repo or IndexerSiteConfigRepositoryAdapter()
        self._site_engine = site_engine or SiteEngine()
        self._idx_config_repo = idx_config_repo or IndexerConfigRepositoryAdapter()

    def _is_indexer_enabled(self, source: str) -> bool:
        """检查索引器是否启用。builtin 默认启用，第三方读 INDEXER_CONFIG 表。"""
        if source == "builtin":
            entity = self._idx_config_repo.get_by_client_id("builtin")
            return entity.enabled if entity else True
        entity = self._idx_config_repo.get_by_client_id(source)
        return entity.enabled if entity else False

    @property
    def site_user_info(self) -> SiteUserInfo:
        """返回站点用户信息组件。"""
        return self._site_user_info

    # ------------------------------------------------------------------
    # 站点属性
    # ------------------------------------------------------------------
    def check_site_attr(self, url: str | None) -> SiteAttrDTO:
        """检查站点标识（FREE / 2XFREE / HR）"""
        site_attr = self._site_conf.get_grap_conf(url)
        return SiteAttrDTO(
            site_free=bool(site_attr.get("FREE")),
            site_2xfree=bool(site_attr.get("2XFREE")),
            site_hr=bool(site_attr.get("HR")),
        )

    # ------------------------------------------------------------------
    # 站点定义
    # ------------------------------------------------------------------
    def get_site_definitions(self) -> list[SiteDefinitionDTO]:
        """返回所有内置站点定义，供前端选择添加站点。"""
        return SiteCatalogService.get_site_definitions(self._site_engine)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_site(self, tid: str | None) -> SiteDetailDTO:
        return SiteCatalogService.get_site(self._sites, self._site_conf, tid)

    def get_site_api_credentials(self, tid: int) -> dict:
        """编辑页按需读取站点凭据；列表接口仍保持脱敏."""
        return SiteCredentialService.get_credentials(self._sites, tid)

    def upsert_site_api_credentials(self, site_id: int, profile: str, data: dict | None) -> None:
        """插件/同步任务写入站点 profile 凭据的公开入口."""
        self._site_entity_repo.upsert_site_api_credentials(int(site_id), str(profile), data)

    @staticmethod
    def _sanitize_site_credentials(site: dict) -> dict:
        return SiteCredentialService.sanitize(site)

    def get_sites(
        self,
        rss: bool = False,
        brush: bool = False,
        statistic: bool = False,
        basic: bool = False,
        source: str | None = None,
    ) -> Any:
        return SiteCatalogService.get_sites(
            sites=self._sites,
            site_engine=self._site_engine,
            indexer_site_config_repo=self._indexer_site_config_repo,
            is_indexer_enabled=self._is_indexer_enabled,
            rss=rss,
            brush=brush,
            statistic=statistic,
            basic=basic,
            source=source,
        )

    @staticmethod
    def _third_party_site_dict(row) -> dict:
        return SiteCatalogService.third_party_site_dict(row)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def delete_site(self, tid: str | None) -> int | None:
        return SiteCrudService.delete_site(
            sites=self._sites,
            site_entity_repo=self._site_entity_repo,
            indexer_site_config_repo=self._indexer_site_config_repo,
            tid=tid,
        )

    def _is_site_duplicate(self, name: str | None, tid: str | None) -> bool:
        return SiteCrudService.is_site_duplicate(self._site_entity_repo, name, tid)

    def update_site(self, data: dict) -> SiteUpdateResultDTO:
        """新增或更新站点信息（使用领域实体 + ISiteRepository）"""
        return SiteCrudService.update_site(
            data=data,
            sites=self._sites,
            site_entity_repo=self._site_entity_repo,
            site_engine=self._site_engine,
            site_user_info=self._site_user_info,
            indexer_site_config_repo=self._indexer_site_config_repo,
        )

    @staticmethod
    def _merge_partial_update(existing, entity: SiteEntity, explicit_fields: set[str]) -> SiteEntity:
        return SiteCrudService.merge_partial_update(existing, entity, explicit_fields)

    def update_site_cookie_ua(self, siteid: int | str, cookie: str, ua: str) -> None:
        SiteCrudService.update_cookie_ua(
            sites=self._sites,
            site_entity_repo=self._site_entity_repo,
            siteid=siteid,
            cookie=cookie,
            ua=ua,
        )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def get_site_activity(self, name: str) -> SiteActivityDTO:
        return SiteStatisticsService.get_activity(self._site_user_info, name)

    def get_site_history(self, days: int, end_day: str | None = None) -> SiteHistoryDTO:
        return SiteStatisticsService.get_history(self._site_user_info, days, end_day)

    def get_site_seeding_info(self, name: str) -> SiteSeedingDTO:
        return SiteStatisticsService.get_seeding(self._site_user_info, name)

    def get_site_daily_history(
        self, days: int = 30, end_day: str | None = None, allowed_sites: set[str] | None = None
    ) -> dict:
        """站点日统计（allowed_sites 非空时仅统计被授权站点，ADR-021 6.1）"""
        return SiteStatisticsService.get_daily_history(
            sites=self._sites,
            site_repo=self._site_repo,
            days=days,
            end_day=end_day,
            allowed_sites=allowed_sites,
        )

    def refresh_site_data_now(self, specify_sites: list | None = None) -> None:
        """强制刷新站点数据"""
        self._site_user_info.refresh_site_data_now(specify_sites=specify_sites)

    def get_site_user_statistics(
        self,
        sites: list | None = None,
        encoding: str = "DICT",
        sort_by: str | None = None,
        sort_on: str | None = None,
        site_hash: str | None = None,
        allowed_sites: set[str] | None = None,
    ) -> list[Any]:
        return SiteStatisticsService.get_user_statistics(
            site_user_info=self._site_user_info,
            sites=self._sites,
            string_utils=self._string_utils,
            sites_filter=sites,
            sort_by=sort_by,
            sort_on=sort_on,
            site_hash=site_hash,
            allowed_sites=allowed_sites,
        )

    # ------------------------------------------------------------------
    # Favicon
    # ------------------------------------------------------------------
    def get_site_favicon(self, name: str | None = None) -> Any:
        return self._site_favicon_service.get_favicon(site_name=name)

    # ------------------------------------------------------------------
    # 连通性测试
    # ------------------------------------------------------------------
    def test_site(self, site_id: int | str) -> SiteTestResultDTO:
        return SiteConnectivityService.test(self._site_resolver, site_id)

    def test_sites_batch(self, site_ids: list[str] | None) -> list[dict[str, Any]]:
        """批量测试站点连通性。

        并发执行，返回每个站点的 {id, flag, msg, times}。不抛异常，单点失败不影响其他站点。
        """
        return SiteConnectivityService.test_batch(self._site_resolver, site_ids)

    # ------------------------------------------------------------------
    # 验证码
    # ------------------------------------------------------------------
    def set_captcha_code(self, code: str, value: str) -> None:
        self._site_cookie.set_code(code=code, value=value)

    # ------------------------------------------------------------------
    # 资源列表
    # ------------------------------------------------------------------
    def list_site_resources(self, index_id: str, page: int, page_size: int, keyword: str) -> SiteResourcesResultDTO:
        return SiteResourceService.list_resources(self._indexer_service, index_id, page, page_size, keyword)

    @staticmethod
    def _attach_media_ident(item: Any) -> None:
        SiteResourceService.attach_media_ident(item)

    def get_site_download_setting(self, site_name: str | None = None) -> Any:
        """获取站点下载设置（代理到 Sites）"""
        return self._sites.get_site_download_setting(site_name=site_name)
