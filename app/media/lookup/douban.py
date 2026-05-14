from app.infrastructure.external.doubanapi import DoubanApi
from app.media.lookup.base import BaseLookup, LookupResult
from app.utils.types import MediaType


class DoubanLookup(BaseLookup):
    """豆瓣查询器 — 直接调用 DoubanApi，不依赖旧模型"""

    def __init__(self):
        self._api = DoubanApi()

    def lookup(self, parsed, hint_type: MediaType = None) -> LookupResult | None:
        name = parsed.title_en or parsed.title_cn
        if not name:
            return None

        search_type = hint_type or parsed.type
        result = self._search(name, search_type, parsed.year)
        if not result:
            return None
        return self._to_lookup_result(result, search_type)

    def _search(self, name, mtype, year):
        """搜索豆瓣并返回最佳匹配"""
        api_result = self._api.search(name)
        if not api_result:
            return None
        items = api_result.get("items") or []
        if not items:
            return None

        for item_obj in items:
            item_type = item_obj.get("type_name")
            if item_type not in (MediaType.MOVIE.value, MediaType.TV.value):
                continue
            if mtype and mtype.value != item_type:
                continue
            item = item_obj.get("target")
            if not item:
                continue
            item_year = str(item.get("year", ""))
            if year and item_year and item_year != str(year):
                continue
            return item
        return items[0].get("target") if items else None

    def _to_lookup_result(self, item, mtype) -> LookupResult | None:
        if not item:
            return None
        did = item.get("id")
        rating = item.get("rating", {}) or {}
        return LookupResult(
            tmdb_id=f"DB:{did}" if did else 0,
            title=item.get("title"),
            original_title=item.get("original_title"),
            media_type=mtype or (MediaType.MOVIE if item.get("type") == "movie" else MediaType.TV),
            year=str(item.get("year", "")),
            overview=item.get("card_subtitle") or "",
            poster_path=item.get("cover_url"),
            vote_average=rating.get("value", 0.0),
            external_ids={"douban_id": did},
        )
