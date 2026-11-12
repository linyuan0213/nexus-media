"""站点统计数据视图."""

from typing import Any, cast

from app.schemas.site import SiteActivityDTO, SiteHistoryDTO, SiteSeedingDTO


class SiteStatisticsService:
    """统计数据读模型；依赖由调用方传入，避免服务持有可变状态."""

    @staticmethod
    def get_activity(site_user_info: Any, name: str) -> SiteActivityDTO:
        dataset = site_user_info.get_pt_site_activity_history(name)
        return SiteActivityDTO(dataset=dataset)

    @staticmethod
    def get_history(site_user_info: Any, days: int, end_day: str | None = None) -> SiteHistoryDTO:
        _, _, site, upload, download = site_user_info.get_pt_site_statistics_history(days + 1, end_day)
        dataset = [["site", "upload", "download"]]
        dataset.extend([[s, u, d] for s, u, d in zip(site, upload, download, strict=False)])
        return SiteHistoryDTO(dataset=dataset)

    @staticmethod
    def get_seeding(site_user_info: Any, name: str) -> SiteSeedingDTO:
        seeding_info = site_user_info.get_pt_site_seeding_info(name).get("seeding_info", [])
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)
        return SiteSeedingDTO(dataset=dataset)

    @staticmethod
    def get_daily_history(
        *,
        sites: Any,
        site_repo: Any,
        days: int = 30,
        end_day: str | None = None,
        allowed_sites: set[str] | None = None,
    ) -> dict:
        """站点日统计（allowed_sites 非空时仅统计被授权站点，ADR-021 6.1）"""
        site_urls = []
        for site in sites.get_sites(statistic=True):
            if allowed_sites is not None and site.get("name") not in allowed_sites:
                continue
            site_url = site.get("strict_url")
            if site_url:
                site_urls.append(site_url)
        return site_repo.get_site_daily_history(days=days, end_day=end_day, strict_urls=site_urls)

    @staticmethod
    def get_user_statistics(
        *,
        site_user_info: Any,
        sites: Any,
        string_utils: Any,
        sites_filter: list | None = None,
        sort_by: str | None = None,
        sort_on: str | None = None,
        site_hash: str | None = None,
        allowed_sites: set[str] | None = None,
    ) -> list[Any]:
        statistics = site_user_info.get_site_user_statistics(sites=sites_filter, encoding="DICT")
        # 按站点授权过滤（ADR-021 6.1；None=不过滤）
        if allowed_sites is not None:
            statistics = [item for item in statistics if cast(dict[str, Any], item).get("site_name") in allowed_sites]
        # 修复馒头站点显示
        for item in statistics:
            item_dict = cast(dict[str, Any], item)
            if "m-team" in item_dict.get("url", ""):
                site_info: Any = sites.get_sites(siteurl=item_dict.get("url")) or {}
                item_dict["url"] = site_info.get("signurl") if isinstance(site_info, dict) else None
        # 排序：sort_by 存在时默认降序，sort_on 显式指定时按指定方向
        if sort_by:
            reverse = sort_on != "asc"
            statistics.sort(key=lambda x: cast(dict[str, Any], x).get(sort_by) or 0, reverse=reverse)
        if site_hash == "Y":
            for item in statistics:
                item_dict = cast(dict[str, Any], item)
                item_dict["site_hash"] = string_utils.md5_hash(item_dict.get("site_name"))
        return statistics
