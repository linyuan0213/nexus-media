"""站点资源列表与离线识别信息."""

from typing import Any

from app.media import meta_info
from app.schemas.site import SiteResourcesResultDTO


class SiteResourceService:
    """索引器资源列表视图."""

    @staticmethod
    def list_resources(
        indexer_service: Any,
        index_id: str,
        page: int,
        page_size: int,
        keyword: str,
    ) -> SiteResourcesResultDTO:
        result = indexer_service.list_resources(index_id=index_id, page=page, page_size=page_size, keyword=keyword)
        data = result.data
        if result.success and isinstance(data, list):
            for item in data:
                SiteResourceService.attach_media_ident(item)
            # 返回 {list, has_more}：has_more 表示本页已满（可能还有下一页），供前端分页导航
            return SiteResourcesResultDTO(
                success=True,
                data={"list": data, "has_more": len(data) >= max(page_size, 1)},
                msg=result.msg,
            )
        return SiteResourcesResultDTO(success=result.success, data=data, msg=result.msg)

    @staticmethod
    def attach_media_ident(item: Any) -> None:
        """为资源列表项附加解析级识别信息（标题离线解析，不走 TMDB）"""
        if not isinstance(item, dict):
            return
        title = item.get("title") or ""
        if not title:
            return
        try:
            mi = meta_info(title=title, subtitle=item.get("description") or "")
        except Exception:  # noqa: BLE001
            return
        item["media"] = {
            "name": mi.get_name() or "",
            "cn_name": mi.cn_name or "",
            "en_name": mi.en_name or "",
            "season_episode": mi.get_season_episode_string(),
            "year": mi.year or "",
            "type": mi.type.value if mi.type else "",
            "resource_type": mi.get_resource_type_string(),
        }
