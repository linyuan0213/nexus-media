import log
from app.indexer.core.models import SearchCandidate
from app.media import MediaService
from app.infrastructure.cache_system import get_cache_manager


class BatchIdentifier:
    """
    批量媒体识别器

    职责：收集需要 TMDB 查询的候选，去重后批量识别，结果写入缓存。
    不直接修改候选对象，仅填充缓存供后续 match_filter 阶段读取。
    """

    def __init__(self, media_service=None):
        self.media = media_service or MediaService()
        self._media_ident_cache = get_cache_manager().get_or_create(
            "media_ident", "memory", maxsize=2000, ttl=3600
        )

    def identify(self, candidates):
        """
        对 candidates 中 skip_tmdb=False 的条目批量查询 TMDB。
        """
        if not candidates:
            return

        to_identify = []
        seen_names = set()

        for cand in candidates:
            if cand.skip_tmdb:
                continue
            meta_info = cand.meta_info
            cache_key = meta_info.get_name() or cand.item.get("title")
            if not cache_key:
                continue
            if self._media_ident_cache.get(cache_key) is not None:
                continue
            if cache_key in seen_names:
                continue
            seen_names.add(cache_key)
            to_identify.append({
                "title": cache_key,
                "subtitle": cand.item.get("description"),
                "site": cand.item.get("site"),
                "enclosure": cand.item.get("enclosure"),
                "size": cand.item.get("size"),
                "seeders": cand.item.get("seeders"),
            })

        if not to_identify:
            return

        log.info(f"【BatchIdentifier】批量识别 {len(to_identify)} 条不重复结果 ...")

        try:
            results = self.media.identify_batch(to_identify)
            for item, info in zip(to_identify, results):
                self._media_ident_cache.set(item["title"], info)
        except Exception as e:
            log.error(f"【BatchIdentifier】批量识别出错: {e}")
