from typing import Optional

from app.media.lookup.base import BaseLookup
from app.media.models import MediaInfo
from app.media.parser.base import BaseParser
from app.media.cache.media_cache import MediaCache


class BatchProcessor:
    """统一批量处理入口 — RSS、索引器、文件扫描共用"""

    def __init__(self, parser: BaseParser, lookup: BaseLookup, cache: MediaCache):
        self.parser = parser
        self.lookup = lookup
        self.cache = cache

    def process(self, items: list[dict]) -> list[Optional[MediaInfo]]:
        if not items:
            return []
        titles = [i.get("title", "") for i in items]
        parsed_list = self.parser.parse_batch(titles)
        results = []
        for idx, item in enumerate(items):
            parsed = parsed_list[idx]
            info = MediaInfo.from_parser(parsed) if parsed else MediaInfo()
            info.site = item.get("site")
            info.enclosure = item.get("enclosure")
            info.size = item.get("size", 0)
            info.seeders = item.get("seeders", 0)
            results.append(info)
        return results
