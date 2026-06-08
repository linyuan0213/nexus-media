import json
from typing import Any, cast

from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.db.repositories.site_repository import SiteRepository
from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
from app.domain.entities.site import SiteEntity
from app.domain.interfaces.site_repo import ISiteRepository
from app.schemas.site import (
    SiteActivityDTO,
    SiteAttrDTO,
    SiteDetailDTO,
    SiteHistoryDTO,
    SiteResourcesResultDTO,
    SiteSeedingDTO,
    SiteTestResultDTO,
    SiteUpdateResultDTO,
)
from app.services.indexer_service import IndexerService
from app.sites import SiteConf, SiteCookie
from app.sites.site_cache import SiteCache
from app.sites.site_userinfo import SiteUserInfo
from app.utils import StringUtils
from app.di import container


class SiteService:
    """站点业务服务：站点 CRUD、统计、连通性测试、资源列表"""

    def __init__(
        self,
        sites: SiteCache | None = None,
        site_user_info: SiteUserInfo | None = None,
        site_conf: SiteConf | None = None,
        site_cookie: SiteCookie | None = None,
        indexer_service: IndexerService | None = None,
        string_utils=None,
        site_repo: SiteRepository | None = None,
        site_entity_repo: ISiteRepository | None = None,
    ):
        self._sites = sites or container.site_cache()
        self._site_user_info = site_user_info or SiteUserInfo()
        self._site_conf = site_conf or container.site_conf()
        self._site_cookie = site_cookie or SiteCookie()
        self._indexer_service = indexer_service or IndexerService()
        self._string_utils = string_utils or StringUtils
        self._site_repo = site_repo or container.site_repository()
        self._site_entity_repo = site_entity_repo or SiteRepositoryAdapter(self._site_repo)

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
    # CRUD
    # ------------------------------------------------------------------
    def delete_site(self, tid: str | None) -> int | None:
        if not tid:
            return 0
        try:
            self._site_entity_repo.delete(int(tid))
            return 1
        except Exception:
            return 0

    def get_site(self, tid: str | None) -> SiteDetailDTO:
        if not tid:
            return SiteDetailDTO(site=[])
        entity = self._site_entity_repo.get_by_id(int(tid))
        if not entity:
            return SiteDetailDTO(site=[])
        site_free = site_2xfree = site_hr = False
        if entity.sign_url:
            attr = self._site_conf.get_grap_conf(entity.sign_url)
            site_free = bool(attr.get("FREE"))
            site_2xfree = bool(attr.get("2XFREE"))
            site_hr = bool(attr.get("HR"))
        return SiteDetailDTO(site=entity.to_dict(), site_free=site_free, site_2xfree=site_2xfree, site_hr=site_hr)

    def get_sites(self, rss: bool = False, brush: bool = False, statistic: bool = False, basic: bool = False) -> Any:
        if basic:
            return self._sites.get_site_dict(rss=rss, brush=brush, statistic=statistic)
        return self._sites.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)

    def _is_site_duplicate(self, name: str | None, tid: str | None) -> bool:
        if not name:
            return False
        sites = self._site_entity_repo.list_by_name(name)
        return any(str(site.id) != str(tid or "") for site in sites)

    def update_site(self, data: dict) -> SiteUpdateResultDTO:
        """新增或更新站点信息（使用领域实体 + ISiteRepository）"""
        tid = data.get("site_id")
        name = data.get("site_name")
        site_pri = data.get("site_pri")
        rssurl = data.get("site_rssurl")
        signurl = data.get("site_signurl")
        cookie = data.get("site_cookie")
        api_key = data.get("site_api_key")
        bearer_token = data.get("site_bearer_token")
        headers = data.get("site_headers")
        note = data.get("site_note")
        if isinstance(note, str):
            try:
                note = json.loads(note)
            except Exception:
                note = {}
        rss_uses = data.get("site_include")

        if self._is_site_duplicate(name, tid):
            return SiteUpdateResultDTO(code=400, msg="站点名称重复")

        entity = SiteEntity(
            id=int(tid) if tid else 0,
            name=name or "",
            pri=int(site_pri) if site_pri else 0,
            rss_url=rssurl,
            sign_url=signurl,
            cookie=cookie,
            api_key=api_key,
            bearer_token=bearer_token,
            headers=headers,
            note=note or {},
            rss_uses=rss_uses,
        )

        if tid:
            existing = self._site_entity_repo.get_by_id(int(tid))
            if not existing:
                return SiteUpdateResultDTO(code=400, msg="站点不存在")
            try:
                self._site_entity_repo.update(entity)
                if name != existing.name and existing.name:
                    self._site_user_info.update_site_name(name, existing.name)
                self._sites.refresh()
                return SiteUpdateResultDTO(code=0)
            except Exception:
                return SiteUpdateResultDTO(code=500)
        else:
            try:
                self._site_entity_repo.insert(entity)
                self._sites.refresh()
                return SiteUpdateResultDTO(code=0)
            except Exception:
                return SiteUpdateResultDTO(code=500)

    def update_site_cookie_ua(self, siteid: int | str, cookie: str, ua: str) -> None:
        self._site_entity_repo.update_cookie_ua(int(siteid), cookie, ua)
        self._sites.refresh()

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def get_site_activity(self, name: str) -> SiteActivityDTO:
        dataset = self._site_user_info.get_pt_site_activity_history(name)
        return SiteActivityDTO(dataset=dataset)

    def get_site_history(self, days: int, end_day: str | None = None) -> SiteHistoryDTO:
        _, _, site, upload, download = self._site_user_info.get_pt_site_statistics_history(days + 1, end_day)
        dataset = [["site", "upload", "download"]]
        dataset.extend([[s, u, d] for s, u, d in zip(site, upload, download, strict=False)])
        return SiteHistoryDTO(dataset=dataset)

    def get_site_seeding_info(self, name: str) -> SiteSeedingDTO:
        seeding_info = self._site_user_info.get_pt_site_seeding_info(name).get("seeding_info", [])
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)
        return SiteSeedingDTO(dataset=dataset)

    def get_site_daily_history(self, days: int = 30, end_day: str | None = None) -> dict:
        site_urls = []
        for site in self._sites.get_sites(statistic=True):
            site_url = site.get("strict_url")
            if site_url:
                site_urls.append(site_url)
        return self._site_repo.get_site_daily_history(days=days, end_day=end_day, strict_urls=site_urls)

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
    ) -> list[Any]:
        statistics = self._site_user_info.get_site_user_statistics(sites=sites, encoding="DICT")
        # 修复馒头站点显示
        for item in statistics:
            item_dict = cast(dict[str, Any], item)
            if "m-team" in item_dict.get("url", ""):
                site_info: Any = self._sites.get_sites(siteurl=item_dict.get("url")) or {}
                item_dict["url"] = site_info.get("signurl") if isinstance(site_info, dict) else None
        # 排序：sort_by 存在时默认降序，sort_on 显式指定时按指定方向
        if sort_by:
            reverse = sort_on != "asc"
            statistics.sort(key=lambda x: cast(dict[str, Any], x).get(sort_by) or 0, reverse=reverse)
        if site_hash == "Y":
            for item in statistics:
                item_dict = cast(dict[str, Any], item)
                item_dict["site_hash"] = self._string_utils.md5_hash(item_dict.get("site_name"))
        return statistics

    # ------------------------------------------------------------------
    # Favicon
    # ------------------------------------------------------------------
    def get_site_favicon(self, name: str | None = None) -> Any:
        return container.site_favicon_service().get_favicon(site_name=name)

    # ------------------------------------------------------------------
    # 连通性测试
    # ------------------------------------------------------------------
    def test_site(self, site_id: int | str) -> SiteTestResultDTO:
        flag, msg, times = container.site_resolver().test_connection(site_id)
        return SiteTestResultDTO(flag=flag, msg=msg, times=times, code=0 if flag else -1)

    # ------------------------------------------------------------------
    # 验证码
    # ------------------------------------------------------------------
    def set_captcha_code(self, code: str, value: str) -> None:
        self._site_cookie.set_code(code=code, value=value)

    # ------------------------------------------------------------------
    # 资源列表
    # ------------------------------------------------------------------
    def list_site_resources(self, index_id: str, page: int, keyword: str) -> SiteResourcesResultDTO:
        result = self._indexer_service.list_resources(index_id=index_id, page=page, keyword=keyword)
        return SiteResourcesResultDTO(success=result.success, data=result.data, msg=result.msg)

    def get_site_download_setting(self, site_name: str | None = None) -> Any:
        """获取站点下载设置（代理到 Sites）"""
        return self._sites.get_site_download_setting(site_name=site_name)
