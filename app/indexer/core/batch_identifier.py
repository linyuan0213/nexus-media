import log
from app.infrastructure.cache_system import get_cache_manager
from app.media import MediaService


class BatchIdentifier:
    """
    批量媒体识别器

    职责：收集需要 TMDB 查询的候选，去重后批量识别，结果写入缓存。
    不直接修改候选对象，仅填充缓存供后续 match_filter 阶段读取。
    """

    def __init__(self, media_service=None):
        self.media = media_service or MediaService()
        self._media_ident_cache = get_cache_manager().get_or_create("media_ident", "memory", maxsize=2000, ttl=3600)

    @staticmethod
    def build_cache_key(meta_info, fallback_title=None):
        """构建与 identify 阶段一致的缓存 key"""
        name = meta_info.get_name() or fallback_title
        if not name:
            return None
        season_ep = ""
        if meta_info.get_season_list():
            season_ep += f"_S{'-'.join(str(s) for s in meta_info.get_season_list())}"
        if meta_info.get_episode_list():
            season_ep += f"_E{'-'.join(str(e) for e in meta_info.get_episode_list())}"
        return f"{name}{season_ep}"

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
            cache_key = self.build_cache_key(cand.meta_info, cand.item.get("title"))
            if not cache_key:
                continue
            if self._media_ident_cache.get(cache_key) is not None:
                continue
            if cache_key in seen_names:
                continue
            seen_names.add(cache_key)
            to_identify.append(
                {
                    "_cache_key": cache_key,
                    "title": cand.item.get("title") or cache_key,
                    "subtitle": cand.item.get("description"),
                    "site": cand.item.get("site"),
                    "enclosure": cand.item.get("enclosure"),
                    "size": cand.item.get("size"),
                    "seeders": cand.item.get("seeders"),
                }
            )

        if not to_identify:
            return

        log.info(f"【BatchIdentifier】批量识别 {len(to_identify)} 条不重复结果 ...")

        try:
            results = self.media.identify_batch(to_identify)
            for item, info in zip(to_identify, results, strict=False):
                self._media_ident_cache.set(item["_cache_key"], info)
        except Exception as e:
            log.error(f"【BatchIdentifier】批量识别出错: {e}")
