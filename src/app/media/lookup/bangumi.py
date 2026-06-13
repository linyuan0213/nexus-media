from app.domain.mediatypes import MediaType
from app.media.external.bangumi import Bangumi
from app.media.lookup.base import BaseLookup, LookupResult


class BangumiLookup(BaseLookup):
    """Bangumi 查询器 — 直接调用 Bangumi API，不依赖旧模型"""

    def __init__(self):
        self._bgm = Bangumi()

    def lookup(self, parsed, hint_type: MediaType | None = None) -> LookupResult | None:
        name = parsed.title_en or parsed.title_cn
        if not name:
            return None

        result = self._search(name)
        if not result:
            return None
        return self._to_lookup_result(result)

    def _search(self, name):
        """从 Bangumi 日历中匹配名称"""
        calendar = self._bgm.calendar()
        if not calendar:
            return None
        name_lower = name.lower()
        for day in calendar:
            for item in day.get("items", []):
                title = item.get("name_cn") or item.get("name", "")
                if name_lower in title.lower() or title.lower() in name_lower:
                    return item
        return None

    def _to_lookup_result(self, item) -> LookupResult | None:
        if not item:
            return None
        bid = item.get("id")
        images = item.get("images") or {}
        rating = item.get("rating") or {}
        air_date = item.get("air_date", "")
        return LookupResult(
            tmdb_id=f"BG:{bid}" if bid else 0,
            title=item.get("name_cn") or item.get("name"),
            original_title=item.get("name"),
            media_type=MediaType.ANIME,
            year=air_date[:4] if air_date else "",
            overview=item.get("summary", ""),
            poster_path=images.get("large"),
            vote_average=rating.get("score", 0.0),
            external_ids={"bangumi_id": bid},
        )
