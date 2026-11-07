from app.domain.media_types import ProviderMediaType, provider_media_type_of
from app.infrastructure.external.doubanapi.apiv2 import DoubanApi
from app.media.lookup.base import BaseLookup, LookupResult


class DoubanLookup(BaseLookup):
    """豆瓣查询器 — 直接调用 DoubanApi，不依赖旧模型"""

    def __init__(self, api: DoubanApi | None = None):
        self._api = api or DoubanApi()

    def lookup(self, parsed, hint_type: ProviderMediaType | None = None) -> LookupResult | None:
        name = parsed.title_en or parsed.title_cn
        if not name:
            return None

        search_type = provider_media_type_of(hint_type or parsed.type)
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

        provider_type = provider_media_type_of(mtype)
        for item_obj in items:
            parsed_type = provider_media_type_of(item_obj.get("type_name"))
            if parsed_type not in (ProviderMediaType.MOVIE, ProviderMediaType.SERIES):
                continue
            if provider_type and parsed_type != provider_type:
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
        provider_type = provider_media_type_of(mtype or item.get("type"))
        return LookupResult(
            tmdb_id=f"DB:{did}" if did else 0,
            title=item.get("title"),
            original_title=item.get("original_title"),
            provider_media_type=provider_type,
            media_kind=provider_type.kind,
            year=str(item.get("year", "")),
            overview=item.get("card_subtitle") or "",
            poster_path=item.get("cover_url"),
            vote_average=rating.get("value", 0.0),
            external_ids={"douban_id": did},
        )
