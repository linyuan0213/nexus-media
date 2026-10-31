import os
from math import floor
from types import SimpleNamespace
from typing import Callable
from urllib.parse import quote

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.display_image_policy import transform_display_image
from app.schemas.media import TransferHistoryPageDTO, UnknownListPageDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.sync_service import SyncService


class TransferHistoryService:
    """
    转移历史业务服务
    """

    def __init__(
        self,
        filetransfer: FileTransfer,
        sync_service: SyncService,
        cache_ttl: int = 30,
        poster_resolver: Callable[[str, int], str] | None = None,
        metadata_service=None,
        subscribe_repo=None,
    ):
        self._filetransfer = filetransfer
        self._sync_service = sync_service
        self._cache = get_cache_manager().get_or_create("transfer_history_service", cache_type="memory", maxsize=100)
        self._cache_ttl = cache_ttl
        # (type, tmdbid) -> 海报 URL；None 表示不富化海报
        self._poster_resolver = poster_resolver
        self._metadata_service = metadata_service
        self._subscribe_repo = subscribe_repo
        # 进程级 memo：同一身份只回源一次，跨页复用
        self._poster_memo: dict[str, str] = {}

    def _resolve_poster(self, history: dict) -> str:
        local_poster = self._local_poster(history)
        if local_poster:
            return local_poster
        # 新记录在转移时已固化海报，旧记录才需要按身份/快照回源。
        stored_poster = str(history.get("POSTER") or "").strip()
        if stored_poster:
            return stored_poster
        identity_id = str(history.get("IDENTITY_ID") or "").strip()
        provider = str(history.get("ANCHOR_PROVIDER") or "").strip()
        external = str(history.get("ANCHOR_EXTERNAL_ID") or "").strip()
        if identity_id or (provider and external):
            key = f"id:{identity_id}" if identity_id else f"{provider}:{external}"
            if key not in self._poster_memo:
                self._poster_memo[key] = self._fallback_poster(history)
            if self._poster_memo[key]:
                return self._poster_memo[key]
        tmdbid = history.get("TMDBID")
        if self._poster_resolver and tmdbid:
            try:
                key = f"tmdb:{int(tmdbid)}"
            except (TypeError, ValueError):
                key = ""
            if key:
                if key not in self._poster_memo:
                    self._poster_memo[key] = self._poster_resolver(str(history.get("TYPE") or ""), int(tmdbid)) or ""
                return self._poster_memo[key]
        return ""

    @staticmethod
    def _build_capabilities(history: dict) -> dict[str, bool]:
        """由服务端裁剪可用动作，前端只按能力渲染."""
        source_state = str(history.get("SOURCE_STATE") or "unknown")
        dest_state = str(history.get("DEST_STATE") or "unknown")
        has_source = bool(history.get("SOURCE_PATH") and history.get("SOURCE_FILENAME"))
        has_dest = bool(history.get("DEST_PATH"))
        source_actionable = has_source and source_state not in ("deleted", "missing")
        dest_actionable = has_dest and dest_state not in ("deleted", "missing")
        return {
            "reidentify": source_actionable,
            "manual_identify": source_actionable,
            "delete_record": True,
            "delete_source": source_actionable,
            "delete_library": dest_actionable,
        }

    @staticmethod
    def _local_poster(history: dict) -> str:
        """媒体目录内已有的 poster.jpg（本地或已挂载后端）."""
        dest_path = str(history.get("DEST_PATH") or "")
        if not dest_path:
            return ""
        local_poster = os.path.join(dest_path, "poster.jpg")
        if os.path.isfile(local_poster):
            return f"/img/poster?path={quote(local_poster, safe='')}"
        return ""

    def _fallback_poster(self, history: dict) -> str:
        """缺本地海报时的统一优先级：订阅图片 → 快照/回源."""
        subscription_poster = self._subscription_poster(history)
        if subscription_poster:
            return subscription_poster
        return self._snapshot_poster(history)

    def _subscription_poster(self, history: dict) -> str:
        """按身份/锚点/标题复用电影订阅海报；非插件订阅无数据时返回空."""
        if self._subscribe_repo is None:
            return ""
        history_type = str(history.get("TYPE") or "").lower()
        if history_type and history_type != MediaType.MOVIE.value:
            return ""
        try:
            hint = self._subscribe_repo.get_movie_subscription_hint(
                history.get("ANCHOR_PROVIDER"),
                history.get("ANCHOR_EXTERNAL_ID"),
                history.get("TITLE"),
                identity_id=history.get("IDENTITY_ID"),
            )
        except Exception:  # noqa: BLE001 - 订阅表不可用不应影响历史展示
            return ""
        if not hint:
            return ""
        if not str(history.get("CONTENT_PROFILE") or "") and hint.get("content_profile"):
            history["CONTENT_PROFILE"] = hint["content_profile"]
        return str(hint.get("image") or "")

    def _snapshot_poster(self, history: dict) -> str:
        if self._metadata_service is None:
            return ""
        try:
            media = SimpleNamespace(
                type=MediaType.from_string(str(history.get("TYPE") or "")),
                anchor_provider=history.get("ANCHOR_PROVIDER"),
                anchor_external_id=history.get("ANCHOR_EXTERNAL_ID"),
                identity_id=history.get("IDENTITY_ID"),
                content_profile=history.get("CONTENT_PROFILE"),
            )
            snapshot = self._metadata_service.latest_snapshot_for_media(media)
            if snapshot is None:
                return ""
            for key in ("poster", "thumb", "cover"):
                for item in (snapshot.images or {}).get(key) or []:
                    if getattr(item, "url", ""):
                        return str(item.url)
            # 旧快照可能只有 refs 没有 images，按 refs 回源补海报。
            for ref in getattr(snapshot, "refs", None) or []:
                provider = str(getattr(ref, "provider", "") or "")
                external_id = str(getattr(ref, "external_id", "") or "")
                if not provider or not external_id or provider in {"content_id", "tmdb", "imdb"}:
                    continue
                record = self._metadata_service.lookup(
                    provider=provider,
                    external_id=external_id,
                    media_type=getattr(ref, "media_type", None),
                    scope=str(getattr(ref, "scope", "") or "default"),
                    content_profile=history.get("CONTENT_PROFILE"),
                    allow_private=True,
                )
                if record is None:
                    continue
                images = record.get("images") if isinstance(record, dict) else getattr(record, "images", None)
                for key in ("poster", "thumb", "cover"):
                    for item in (images or {}).get(key) or []:
                        url = item.get("url") if isinstance(item, dict) else getattr(item, "url", "")
                        if url:
                            return str(url)
        except Exception:  # noqa: BLE001
            return ""
        return ""

    def _cache_key(self, prefix: str, *parts) -> str:
        return f"{prefix}:{':'.join(str(p) for p in parts)}"

    def get_transfer_history_page(self, search_str, page, page_num, media_type=None) -> TransferHistoryPageDTO:
        """分页查询转移历史（带缓存）"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        cache_key = self._cache_key("history", search_str or "", media_type or "", page, page_num)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._filetransfer.get_transfer_history(search_str, page, page_num, media_type)
        if result is None:
            total_count, historys = 0, []
        else:
            total_count, historys = result
        historys_list = []
        for history in historys:
            history = history.as_dict()
            sync_mode = history.get("mode")
            rmt_mode = sync_mode or ""
            history = {k.upper(): v for k, v in history.items()}
            history.update({"SYNC_MODE": sync_mode, "RMT_MODE": rmt_mode})
            history["SOURCE_STATE"] = history.get("SOURCE_STATE") or "unknown"
            history["DEST_STATE"] = history.get("DEST_STATE") or "unknown"
            history["CAPABILITIES"] = self._build_capabilities(history)
            # 海报富化：同 (type, tmdbid) 进程内只解析一次，缺 TMDBID/无解析器则跳过
            history["image"] = ""
            poster = self._resolve_poster(history)
            if poster:
                if not str(history.get("POSTER") or "").strip():
                    self._filetransfer.update_transfer_history_poster(history.get("ID"), poster)
                    history["POSTER"] = poster
                history["image"] = transform_display_image(
                    str(history.get("CONTENT_PROFILE") or ""),
                    poster,
                )
            historys_list.append(history)
        total_page = floor(total_count / page_num) + 1
        dto = TransferHistoryPageDTO(
            total=total_count, result=historys_list, total_page=total_page, page_num=page_num, current_page=page
        )
        self._cache.set(cache_key, dto, ttl=self._cache_ttl)
        return dto

    def get_transfer_statistics(self, days=90) -> dict:
        """获取转移统计（带缓存）"""
        cache_key = self._cache_key("stats", days)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        data = {}
        for statistic in self._filetransfer.get_transfer_statistics(days) or []:
            if not statistic[2]:
                continue
            label = statistic[1]
            parsed = MediaType.from_string(statistic[0])
            if parsed not in (MediaType.MOVIE, MediaType.TV, MediaType.ANIME):
                continue
            entry = data.setdefault(label, {"movie": 0, "tv": 0, "anime": 0})
            if parsed == MediaType.MOVIE:
                entry["movie"] = statistic[2]
            elif parsed == MediaType.TV:
                entry["tv"] = statistic[2]
            elif parsed == MediaType.ANIME:
                entry["anime"] = statistic[2]
        labels = list(data.keys())
        # 按天去重剧数（仅电视剧，用于首页卡片趋势口径对齐）
        series_by_date = {s[0]: s[1] for s in self._filetransfer.get_transfer_series_statistics(days) or []}
        result = {
            "labels": labels,
            "movie_nums": [data[label]["movie"] for label in labels],
            "tv_nums": [data[label]["tv"] for label in labels],
            "anime_nums": [data[label]["anime"] for label in labels],
            "tv_series_nums": [series_by_date.get(label, 0) for label in labels],
        }
        self._cache.set(cache_key, result, ttl=self._cache_ttl)
        return result

    def _convert_unknown_record(self, rec) -> dict | None:
        """将未识别记录转换为前端需要的字典结构."""
        rec_path = str(rec.PATH or "")
        if not rec_path:
            return None
        path = rec_path.replace("\\", "/")
        path_to = str(rec.DEST or "").replace("\\", "/")
        sync_mode = str(rec.MODE or "")
        return {
            "id": rec.ID,
            "path": path,
            "to": path_to,
            "name": path,
            "sync_mode": sync_mode,
            "rmt_mode": sync_mode,
            "dst_backend": self._filetransfer.get_sync_backend_by_dest(path_to),
        }

    def _prune_missing_unknown(self) -> None:
        """刷新时清理硬盘上已不存在的未识别记录."""
        try:
            records = self._filetransfer.get_transfer_unknown_paths() or []
            missing = [int(rec.ID) for rec in records if rec.PATH and not os.path.exists(str(rec.PATH))]
            if missing:
                self._filetransfer.delete_transfer_unknowns(missing)
                self._cache.clear()
                log.info(f"[TransferHistory]清理已不存在的未识别记录: {len(missing)}")
        except Exception as e:  # noqa: BLE001 - 清理失败不影响列表读取
            log.warn(f"[TransferHistory]检查未识别文件失败: {e}")

    def get_unknown_list(self) -> list[dict]:
        """获取未识别记录列表（带缓存）"""
        self._prune_missing_unknown()
        cache_key = self._cache_key("unknown_list")
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        items = []
        for rec in self._filetransfer.get_transfer_unknown_paths() or []:
            item = self._convert_unknown_record(rec)
            if item:
                items.append(item)
        self._cache.set(cache_key, items, ttl=self._cache_ttl)
        return items

    def get_unknown_list_by_page(self, search_str, page, page_num) -> UnknownListPageDTO:
        """分页查询未识别记录（带缓存）"""
        self._prune_missing_unknown()
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        cache_key = self._cache_key("unknown_page", search_str or "", page, page_num)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result2 = self._filetransfer.get_transfer_unknown_paths_by_page(search_str, page, page_num)
        if result2 is None:
            total_count, records = 0, []
        else:
            total_count, records = result2
        items = []
        for rec in records:
            item = self._convert_unknown_record(rec)
            if item:
                items.append(item)
        total_page = floor(total_count / page_num) + 1
        dto = UnknownListPageDTO(
            total=total_count, items=items, total_page=total_page, page_num=page_num, current_page=page
        )
        self._cache.set(cache_key, dto, ttl=self._cache_ttl)
        return dto

    def re_identify_unknown(self) -> int:
        """重新识别所有未识别记录"""
        item_ids = [rec.ID for rec in self._filetransfer.get_transfer_unknown_paths() or [] if rec.PATH]
        if item_ids:
            self._sync_service.re_identify_items(flag="unidentification", ids=item_ids)
        return len(item_ids)

    def invalidate_cache(self) -> None:
        """失效历史/统计缓存（批量改名后调用）."""
        self._cache.clear()

    def clear_history(self):
        """清空识别记录"""
        self._filetransfer.delete_transfer()
        self._filetransfer.truncate_transfer_blacklist()
        self._cache.clear()
