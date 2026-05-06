from concurrent.futures import ThreadPoolExecutor

import log
from app.indexer.core.models import SearchCandidate
from app.media import Media
from app.utils.cache_system import get_cache_manager


class BatchIdentifier:
    """
    批量媒体识别器

    职责：收集需要 TMDB 查询的候选，去重后并发识别，结果写入缓存。
    不直接修改候选对象，仅填充缓存供后续 match_filter 阶段读取。
    """

    def __init__(self, media=None, max_workers=4):
        self.media = media or Media()
        self.max_workers = max_workers
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
            to_identify.append((cache_key, cand.item.get("description")))

        if not to_identify:
            return

        log.info(f"【BatchIdentifier】并发识别 {len(to_identify)} 条不重复结果 ...")

        def _do_identify(args):
            name, desc = args
            try:
                return name, self.media.get_media_info(title=name, subtitle=desc, chinese=False)
            except Exception as e:
                log.error(f"【BatchIdentifier】识别出错: {name}, {e}")
                return name, None

        max_workers = min(len(to_identify), self.max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for name, media_info in executor.map(_do_identify, to_identify):
                if media_info:
                    self._media_ident_cache.set(name, media_info)
