"""SearchOrchestrator — 统一搜索编排器。

合并 Web 搜索、交互式搜索、订阅搜索三条路径的公共逻辑：
关键词解析 → TMDB 识别 → 并发搜索 → Pipeline 过滤 → 去重排序 → 入库 → 可选下载。
所有结果按 session_id 隔离存储，新搜索覆盖旧结果。
"""

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

import log
from app.core.settings import settings
from app.db.engine import background_engine_context
from app.domain.enums import SearchType, channel_name
from app.domain.interfaces.download_repo import IDownloadHistoryRepository
from app.domain.interfaces.intent import IntentResolver
from app.domain.interfaces.search_repo import ISearchRepository
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.bus import EventBus
from app.events.constants import SEARCH_START
from app.events.payloads import SearchStartPayload
from app.infrastructure.progress import CompositeProgressGroup, ProgressTracker
from app.media import meta_info
from app.media.image_resolver import DEFAULT_TMDB_IMAGE
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.media.service import MediaService
from app.message import Message
from app.services.downloader_core import DownloaderCore as Downloader
from app.services.search_context import SearchContext
from app.services.search_service import SearchQueryBuilder, SearchResultDeduplicator, SearchResultProcessor
from app.utils import StringUtils

# 默认站点 tier 的排序抬升量，必须大于 site_priority_order 的最大值（9999）
SITE_TIER_BOOST = 100_000


class SearchOrchestrator:
    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        searcher,  # Searcher
        search_repo: ISearchRepository,
        download_repo: IDownloadHistoryRepository,
        downloader: Downloader,
        media_service: MediaService,
        message: Message,
        progress_helper: ProgressTracker,
        event_bus: EventBus,
        intent_resolver: IntentResolver | None = None,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._searcher = searcher
        self._search_repo = search_repo
        self._download_repo = download_repo
        self._downloader = downloader
        self._media = media_service
        self._message = message
        self._progress = progress_helper
        self._event_bus = event_bus
        self._intent_resolver = intent_resolver
        self._metadata_gateway = metadata_gateway
        self._search_auto = settings.get("pt").get("search_auto", True)

    @property
    def _metadata(self):
        return self._metadata_gateway

    @staticmethod
    def _metadata_context(content_profile: str | None = None, allow_private: bool = True) -> MetadataContext:
        return MetadataContext(
            purpose="search",
            allow_private=allow_private,
            content_profile=str(content_profile or "default"),
        )

    def _metadata_lookup(self, provider: str, external_id: str, *, context=None, **kwargs):
        if self._metadata_gateway is None:
            return None
        allow_private = bool(kwargs.pop("allow_private", True))
        kwargs["context"] = context or self._metadata_context(kwargs.get("content_profile"), allow_private)
        return self._metadata_gateway.lookup(provider, external_id, **kwargs)

    def _metadata_search(self, *, context=None, **kwargs):
        if self._metadata_gateway is None:
            return []
        allow_private = bool(kwargs.pop("allow_private", True))
        kwargs["context"] = context or self._metadata_context(kwargs.get("content_profile"), allow_private)
        return self._metadata_gateway.search(**kwargs)

    def _metadata_hydrate(self, media_info) -> None:
        if self._metadata_gateway is not None:
            self._metadata_gateway.hydrate_media(media_info, context=self._metadata_context())

    def begin_search(self, session_id: str, keyword: str = "") -> None:
        """解析锚点元数据前先建立进度，避免 SSE 因长时间无记录提前断开."""
        progress_key = f"search:{session_id or 'web'}"
        self._progress.start(progress_key)
        text = f"正在解析 {keyword} 的媒体信息..." if keyword else "正在解析媒体信息..."
        self._progress.update(value=1, text=text, ptype=progress_key)

    def end_search(self, session_id: str) -> None:
        """确保搜索任务任何退出路径都会关闭进度，前端不会停在 0%."""
        self._progress.end(f"search:{session_id or 'web'}")

    @staticmethod
    def _apply_site_tier(media_list: list, filter_args: dict | None) -> list:
        """默认站点 tier：整体抬升 site_order，保证不被更高全局优先级的补充站点压过."""
        tier_sites = (filter_args or {}).get("site_tier")
        if not tier_sites:
            return media_list
        tier = {str(site) for site in tier_sites if str(site)}
        for media in media_list:
            if str(getattr(media, "site", "") or "") in tier:
                media.site_order = int(getattr(media, "site_order", 0) or 0) + SITE_TIER_BOOST
        return media_list

    def _finish_progress(self, progress_key: str, site_count: int, total: int) -> None:
        """全部后处理完成后再置 100%，避免前端在 100% 时仍看到加载态."""
        self._progress.update_max(
            value=100,
            text=(
                f"关键词完成 {site_count}/{site_count} · 搜索完成，共 {total} 条"
                f"{self._failed_sites_summary(progress_key)}"
            ),
            ptype=progress_key,
        )
        self._progress.end(progress_key)

    def orchestrate(self, ctx: SearchContext) -> tuple[Any | None, dict | None, int, int]:
        progress_key: str = f"search:{ctx.session_id}"
        self._progress.start(progress_key)
        self._progress.update(value=2, text="准备搜索...", ptype=progress_key)

        # 1. 构建搜索词和过滤条件
        search_names, max_workers, filter_args = self._prepare_search(ctx)
        if not search_names:
            self._progress.end(progress_key)
            return None, ctx.no_exists or {}, 0, 0

        # 2. 并发搜索
        media_list = self._execute_searches(ctx, search_names, max_workers, filter_args)

        # 3. 去重
        media_list = SearchResultDeduplicator.deduplicate(media_list)
        media_list = self._apply_site_tier(media_list, filter_args)

        if not media_list:
            log.info(f"[Orchestrator]{ctx.keyword} 未搜索到任何资源")
            self._progress.end(progress_key)
            return None, ctx.no_exists or {}, 0, 0

        # 4. 排序（复用 SearchResultProcessor，全系统统一排序键；尊重做种数/站点优先规则）
        self._progress.update_max(
            value=95,
            text=f"关键词完成 {len(search_names)}/{len(search_names)} · 排序 {len(media_list)} 条结果...",
            ptype=progress_key,
        )
        media_list = SearchResultProcessor.sort_results(
            media_list, download_order=(settings.get("pt") or {}).get("download_order")
        )

        # 5. 入库
        if ctx.persist:
            self._enrich_and_persist(ctx, media_list)

        self._progress.update_max(
            value=95,
            text=f"关键词完成 {len(search_names)}/{len(search_names)} · 正在整理结果...",
            ptype=progress_key,
        )

        # 6. 过滤已下载
        filtered = self._filter_downloaded(media_list)
        if not filtered:
            log.info("[Orchestrator]所有搜索结果已在下载历史中存在")
            self._finish_progress(progress_key, len(search_names), len(media_list))
            return None, ctx.no_exists or {}, len(media_list), 0

        # 7. 择优下载
        if ctx.auto_download and filtered:
            download_items, left_medias = self._downloader.batch_download(
                in_from=ctx.search_type,
                media_list=filtered,
                need_tvs=ctx.no_exists,
                user_name=ctx.user_name,
                user_id=ctx.user_id,
            )
            if download_items:
                total = len(media_list)
                dl_count = len(download_items)
                log.info(f"[Orchestrator]下载了 {dl_count}/{total} 个资源")
                result_no_exists = left_medias if left_medias is not None else (ctx.no_exists or {})
                self._finish_progress(progress_key, len(search_names), total)
                return download_items[0], result_no_exists, total, dl_count

        self._finish_progress(progress_key, len(search_names), len(media_list))
        return None, ctx.no_exists or {}, len(media_list), 0

    def resolve_anchor_media(
        self,
        anchor_provider: str,
        anchor_external_id: str,
        media_type: MediaType | None = None,
        content_profile: str | None = None,
        context: MetadataContext | None = None,
    ):
        """按新锚点模型读取独立元数据源，不经过 TMDB/旧 DB: 转换."""
        service = self._metadata
        if service is None or not anchor_provider or not anchor_external_id:
            return None
        try:
            record = self._metadata_lookup(
                anchor_provider,
                str(anchor_external_id),
                media_type=media_type,
                content_profile=content_profile or "default",
                allow_private=True,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001 - 来源失败由调用方决定回退
            log.warn(f"[Orchestrator]锚点元数据读取失败 {anchor_provider}:{anchor_external_id}: {exc}")
            return None
        if not isinstance(record, dict):
            return None
        title = str(record.get("title") or record.get("name") or "").strip()
        if not title:
            return None
        actual_type = media_type or MediaType.from_string(str(record.get("media_type") or "")) or MediaType.TV
        genres = record.get("genres") or []
        genre_names = [str(item.get("name") if isinstance(item, dict) else item).strip() for item in genres if item]
        if actual_type == MediaType.TV and any(name in {"动画", "动漫", "アニメ", "Animation"} for name in genre_names):
            actual_type = MediaType.ANIME
        info = meta_info(title=title, mtype=actual_type)
        info.title = title
        has_cjk = any("\u4e00" <= char <= "\u9fff" for char in title)
        info.cn_name = title if has_cjk else None
        aliases = [str(item).strip() for item in (record.get("aliases") or []) if str(item).strip()]
        original_title = str(record.get("original_title") or "").strip()
        latin_aliases = [item for item in aliases if any("a" <= ch.lower() <= "z" for ch in item)]
        original_is_latin = bool(original_title) and not any("\u4e00" <= ch <= "\u9fff" for ch in original_title)
        # 优先 official original_title，别名里的 "Resident Evil 0" 只是地区/暂定名
        latin_alias = (
            original_title
            if original_is_latin
            else next((item for item in latin_aliases if not re.search(r"\s0$", item)), "")
        )
        info.en_name = None if has_cjk else title
        if not info.en_name and latin_alias:
            info.en_name = latin_alias
        info.aliases = aliases
        info.original_title = original_title or title
        if actual_type in (MediaType.TV, MediaType.ANIME) and info.begin_season is None and title:
            # 豆瓣等单季条目把季写在标题里：解析成真实季号，供匹配和过滤使用。
            _, _, title_season, _, _, _ = StringUtils.get_keyword_from_string(title)
            if title_season:
                info.begin_season = int(title_season)
        info.original_language = str(record.get("original_language") or "")
        raw_year = str(record.get("year") or "").strip()
        info.year = "" if raw_year in ("", "0", "0000") else raw_year
        info.overview = str(record.get("overview") or "")
        info.anchor_provider = anchor_provider
        info.anchor_external_id = str(anchor_external_id)
        info.content_profile = content_profile or str(record.get("content_profile") or "default")
        info.tmdb_id = str(anchor_external_id) if anchor_provider == "tmdb" else ""
        images = record.get("images") or {}
        poster = (images.get("poster") or [None])[0] if isinstance(images, dict) else None
        if poster:
            info.poster_path = str(poster.get("url") if isinstance(poster, dict) else poster)
        return info

    def resolve_content_id_media(
        self,
        provider: str,
        content_id: str,
        media_type: MediaType | None = None,
        content_profile: str | None = None,
        context: MetadataContext | None = None,
    ):
        """用选定 provider 搜索内容编号，再用命中的 provider 详情 ID 解析."""
        service = self._metadata
        if service is None or not content_id:
            return None
        try:
            hits = self._metadata_search(
                query=str(content_id),
                provider=provider or None,
                media_type=media_type,
                content_profile=content_profile or "default",
                limit=5,
                allow_private=True,
                wait_timeout=40,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Orchestrator]编号搜索失败 {provider}:{content_id}: {exc}")
            hits = []
        if not hits and provider:
            # 指定来源临时超时/熔断时，用同编号在全部可用来源中兜底解析。
            try:
                hits = self._metadata_search(
                    query=str(content_id),
                    provider=None,
                    media_type=media_type,
                    content_profile=content_profile or "default",
                    limit=5,
                    allow_private=True,
                    wait_timeout=40,
                    context=context,
                )
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[Orchestrator]编号跨来源搜索失败 {content_id}: {exc}")
                hits = []
        for hit in hits or []:
            ref = hit.get("ref") or {}
            hit_provider = str(ref.get("provider") or provider)
            hit_external = str(ref.get("external_id") or "")
            if not hit_external:
                continue
            media = self.resolve_anchor_media(
                hit_provider,
                hit_external,
                media_type=media_type,
                content_profile=content_profile,
                context=context,
            )
            if media is not None:
                # 保留真实来源，content_id 只是内部定位锚点，不能覆盖通知/详情来源。
                media.provider = hit_provider
                media.metadata_ref = f"{hit_provider}:{hit_external}"
                media.anchor_provider = "content_id"
                media.anchor_external_id = str(content_id)
                return media
        return None

    @staticmethod
    def _provider_title(media_info) -> str:
        data = getattr(media_info, "provider_data", None)
        if data is None or not hasattr(data, "get"):
            return ""
        return str(
            data.get("name") or data.get("title") or data.get("original_name") or data.get("original_title") or ""
        )

    @classmethod
    def identity_matches_keyword(cls, media_info, keyword: str) -> bool:
        """锚点身份是否与当前关键词一致（覆盖 provider_data 与本地字段）."""

        def norm(value: str) -> str:
            return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())

        wanted = norm(keyword)
        if not wanted:
            return True
        candidates: list[str] = []
        for key in ("title", "cn_name", "en_name", "original_title"):
            value = getattr(media_info, key, None)
            if value:
                candidates.append(str(value))
        for alias in getattr(media_info, "aliases", None) or []:
            if alias:
                candidates.append(str(alias))
        data = getattr(media_info, "provider_data", None)
        if data is not None and hasattr(data, "get"):
            for key in ("name", "title", "original_name", "original_title", "cn_name", "zh_name"):
                value = data.get(key)
                if value:
                    candidates.append(str(value))
            for key in ("aliases", "aka", "alternative_titles"):
                value = data.get(key)
                if isinstance(value, dict):
                    value = value.get("titles") or value.get("results") or []
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            item = item.get("title") or item.get("name")
                        if item:
                            candidates.append(str(item))
        return any(
            wanted in norm(candidate) or norm(candidate) in wanted for candidate in candidates if norm(candidate)
        )

    @staticmethod
    def _provider_title_matches(media_info, keyword: str) -> bool:
        """防止错误 TMDB 映射把搜索词改成无关影片."""
        data = getattr(media_info, "provider_data", None)
        if data is None or not hasattr(data, "get"):
            return False

        def norm(value: str) -> str:
            return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())

        wanted = norm(keyword)
        if not wanted:
            return False
        candidates: list[str] = []
        for key in ("name", "title", "original_name", "original_title", "cn_name", "zh_name"):
            value = data.get(key)
            if value:
                candidates.append(str(value))
        for key in ("aliases", "aka", "alternative_titles"):
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("titles") or value.get("results") or []
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        item = item.get("title") or item.get("name")
                    if item:
                        candidates.append(str(item))
        return any(
            wanted in norm(candidate) or norm(candidate) in wanted for candidate in candidates if norm(candidate)
        )

    def _prepare_search(self, ctx: SearchContext) -> tuple[list[str], int, dict]:
        media_info = ctx.match_media

        explicit_anchor = bool(
            getattr(media_info, "anchor_provider", "") and str(getattr(media_info, "anchor_provider", "")) != "tmdb"
        )
        if (
            media_info
            and media_info.provider_data
            and not explicit_anchor
            and not self._provider_title_matches(media_info, ctx.keyword)
        ):
            log.warn(
                f"[Orchestrator]识别结果与关键词不匹配，丢弃身份: 搜索名={ctx.keyword}, "
                f"provider标题={self._provider_title(media_info)}"
            )
            media_info = None
            ctx.match_media = None

        if not media_info:
            media_info = self._identify_media(ctx)
            if media_info and media_info.provider_data and not self._provider_title_matches(media_info, ctx.keyword):
                log.warn(
                    f"[Orchestrator]首次识别标题不匹配，按 TV 重试: 搜索名={ctx.keyword}, "
                    f"provider标题={self._provider_title(media_info)}"
                )
                retry = self._identify_media(ctx, force_type=MediaType.TV)
                media_info = (
                    retry
                    if retry and retry.provider_data and self._provider_title_matches(retry, ctx.keyword)
                    else None
                )
            ctx.match_media = media_info

        if media_info:
            search_names, max_workers = SearchQueryBuilder.build_search_names(media_info, self._media)
            search_season = media_info.get_season_list() if media_info.begin_season is not None else None
            search_episode = media_info.get_episode_list()
            if ctx.search_type == SearchType.WEB:
                # 手动资源搜索：标题里的“第二季/S02”作为匹配季，母标题用于召回；
                # 没有季标记时才按整部剧召回。
                if not (ctx.filter_args or {}).get("season"):
                    title_season = None
                    if media_info.type in (MediaType.TV, MediaType.ANIME):
                        _, _, title_season, _, _, _ = StringUtils.get_keyword_from_string(
                            str(media_info.title or media_info.cn_name or "")
                        )
                    search_season = [int(title_season)] if title_season else None
                if not (ctx.filter_args or {}).get("episode"):
                    search_episode = None
            if search_episode and not search_season:
                search_season = [1]
            filter_args = {
                "season": search_season,
                "episode": search_episode,
                "year": media_info.year,
                "type": media_info.type.value if media_info.type else None,
            }
            if ctx.filter_args:
                filter_args.update(ctx.filter_args)
            log.info(f"[Orchestrator]搜索名={ctx.keyword}, 实际搜索词={search_names}")
            return search_names, min(max_workers, 8), self._inject_user(ctx, filter_args)

        base = {
            "season": None,
            "episode": None,
            "year": None,
            "type": ctx.media_type.value if ctx.media_type else None,
        }
        if ctx.filter_args:
            base.update(ctx.filter_args)
        log.info(f"[Orchestrator]搜索名={ctx.keyword}, 无有效 provider 身份，按原关键词搜索")
        return [ctx.keyword], 1, self._inject_user(ctx, base)

    @staticmethod
    def _inject_user(ctx: SearchContext, filter_args: dict) -> dict:
        """将搜索归属用户注入 filter_args，供索引器层做站点授权过滤"""
        if ctx.user_id:
            filter_args["user_id"] = ctx.user_id
        return filter_args

    def _identify_media(self, ctx: SearchContext, force_type: MediaType | None = None) -> Any:
        try:
            if self._intent_resolver:
                intent = self._intent_resolver.resolve(ctx.keyword)
                mtype = MediaType.from_string(intent.media_type) if intent.media_type else None
                # TMDB 无动漫类型，识别按电视剧处理（与旧 Web 流水线一致）
                if mtype == MediaType.ANIME:
                    mtype = MediaType.TV
                season_num = intent.season
                episode_num = intent.episode
                keyword = intent.keywords or ctx.keyword
            else:
                mtype, key_word, season_num, episode_num, _year, content = StringUtils.get_keyword_from_string(
                    ctx.keyword
                )
                keyword = content or key_word or ctx.keyword
            if force_type:
                mtype = force_type
            elif ctx.media_type:
                mtype = ctx.media_type
            ident = self._media.get_media_info(mtype=mtype, title=keyword, cache=False)
            if ident and ident.provider_data:
                if season_num:
                    ident.begin_season = int(season_num)
                if episode_num:
                    ident.begin_episode = int(episode_num)
                log.info(f"[Orchestrator]TMDB 识别: {ident.get_title_string()}")
                return ident
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Orchestrator]TMDB 识别失败: {e}")
        return None

    def _execute_searches(
        self, ctx: SearchContext, search_names: list[str], max_workers: int, filter_args: dict
    ) -> list:
        media_list = []
        progress_key: str = f"search:{ctx.session_id}"
        total = len(search_names)
        filter_args = {**filter_args, "progress_key": progress_key}
        group = CompositeProgressGroup(self._progress, progress_key, total, "搜索")

        if max_workers <= 1 and total == 1:
            child = group.child(0)
            task_args = {**filter_args, "progress_child": child}
            result = self._search_one(SearchType.WEB, search_names[0], task_args, ctx.match_media)
            if result:
                media_list.extend(result)
            group.complete_child(0, f"找到 {len(media_list)} 条")
            return media_list

        with self._search_executor(max_workers) as executor:
            tasks = []
            for index, name in enumerate(search_names):
                child = group.child(index)
                task_args = {**filter_args, "progress_child": child}
                tasks.append(
                    (
                        index,
                        executor.submit(self._search_one_background, SearchType.WEB, name, task_args, ctx.match_media),
                    )
                )

            for index, future in tasks:
                result = future.result()
                group.complete_child(index, f"找到 {len(result or [])} 条")
                if result:
                    if isinstance(result, list):
                        media_list.extend(result)
                    else:
                        media_list.append(result)

        return media_list

    def _search_one_background(self, in_from: SearchType, key_word: str, filter_args: dict, match_media: Any) -> list:
        """搜索线程使用后台连接池，避免占满 API 主池。"""
        with background_engine_context():
            return self._search_one(in_from, key_word, filter_args, match_media)

    def _search_one(self, in_from: SearchType, key_word: str, filter_args: dict, match_media: Any) -> list:
        if not key_word or not self._searcher.indexer_service:
            return []
        if self._event_bus:
            self._event_bus.publish(
                Event(
                    event_type=SEARCH_START,
                    payload=SearchStartPayload(
                        key_word=key_word,
                        media_info=match_media.to_dict() if match_media else None,
                        filter_args=filter_args,
                        search_type=channel_name(in_from),
                    ),
                )
            )
        return self._searcher.indexer_service.search_by_keyword(
            key_word=key_word, filter_args=filter_args, match_media=match_media, in_from=in_from
        )

    @staticmethod
    def _sort_results(media_list: list) -> list:
        """已归并到 SearchResultProcessor.sort_results，保留以兼容外部调用"""
        return SearchResultProcessor.sort_results(
            media_list, download_order=(settings.get("pt") or {}).get("download_order")
        )

    def _filter_downloaded(self, media_list: list) -> list:
        filtered = []
        for media_item in media_list:
            if media_item.tmdb_id:
                season_episode = media_item.get_season_episode_string()
                if self._download_repo.is_completed_by_tmdb(media_item.tmdb_id, season_episode):
                    log.info(f"[Orchestrator]{media_item.title} {season_episode} 已下载，跳过")
                    continue
            filtered.append(media_item)
        return filtered

    def _enrich_and_persist(self, ctx: SearchContext, media_list: list):
        # 从匹配媒体注入海报/简介/评分到每条搜索结果
        match_media = ctx.match_media
        if match_media:
            if not match_media.get_poster_image() and self._metadata is not None:
                self._hydrate_with_timeout(match_media)
            poster_url = match_media.get_poster_image()
            overview = match_media.overview
            vote = match_media.vote_average
            for mi in media_list:
                current_poster = mi.get_poster_image()
                if poster_url and (not current_poster or str(current_poster) == DEFAULT_TMDB_IMAGE):
                    mi.poster_path = poster_url
                if overview and not mi.overview:
                    mi.overview = overview
                if vote and not mi.vote_average:
                    mi.vote_average = vote
                # 结果行必须继承锚点的媒体类型和身份，否则资源卡片/入库会退回默认 movie。
                if match_media.type != MediaType.UNKNOWN:
                    if match_media.type in (MediaType.MOVIE, MediaType.ANIME):
                        mi.type = match_media.type
                    elif mi.type not in (MediaType.TV, MediaType.ANIME):
                        mi.type = match_media.type
                if not getattr(mi, "anchor_provider", None):
                    mi.anchor_provider = getattr(match_media, "anchor_provider", None)
                if not getattr(mi, "anchor_external_id", None):
                    mi.anchor_external_id = getattr(match_media, "anchor_external_id", None)
                if not getattr(mi, "identity_id", None):
                    mi.identity_id = getattr(match_media, "identity_id", None)
                if not getattr(mi, "content_profile", None) or str(mi.content_profile) == "default":
                    mi.content_profile = getattr(match_media, "content_profile", None) or "default"
                if not getattr(mi, "tmdb_id", None) and match_media.tmdb_id:
                    mi.tmdb_id = match_media.tmdb_id

        self._persist_results(ctx, media_list)

    def _hydrate_with_timeout(self, match_media, timeout: float = 5.0) -> None:
        """海报补全是有界增强，不能阻塞搜索入库；超时先返回已有数据."""
        if self._metadata is None:
            return
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="search_hydrate")

        def _hydrate():
            with background_engine_context():
                self._metadata_hydrate(match_media)

        future = executor.submit(_hydrate)
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            log.warn(f"[Orchestrator]海报补全超时 {timeout:.0f}s，先返回搜索结果")
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Orchestrator]海报补全失败: {exc}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _persist_results(self, ctx: SearchContext, media_list: list):
        # session_id 已经是天然隔离键，不能再使用全局锁；并发会话各自写自己的 session。
        self._search_repo.delete_by_session(ctx.session_id)
        self._search_repo.insert_search_results(media_list, ctx.keyword, ctx.ident_flag, ctx.session_id, ctx.user_id)

    def _failed_sites_summary(self, progress_key: str) -> str:
        """从搜索进度中汇总失败站点（error/timeout），用于"搜索完成"文本"""
        try:
            detail = self._progress.get_process(progress_key)
            sites = detail.get("sites") if detail else None
            if not sites:
                return ""
            failed = [s for s in sites if s.get("status") in ("error", "timeout")]
            if not failed:
                return ""
            return "；失败站点：" + "、".join(f"{s['name']}({s.get('error') or s['status']})" for s in failed)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Orchestrator]失败站点汇总失败: {e}")
            return ""

    def get_results(self, session_id: str, user_id: str | None = None) -> list:
        if self._search_repo is None:
            return []
        return self._search_repo.get_search_results(session_id, user_id)

    def get_progress(self, session_id: str) -> dict | None:
        session_detail = self._progress.get_process(f"search:{session_id}")
        # session 已结束 → 返回结束状态，防止重新开启
        if session_detail and not session_detail.get("enable") and session_detail.get("value", 0) >= 100:
            return session_detail
        return session_detail

    def cleanup_expired_sessions(self, ttl_hours: int = 24):
        self._search_repo.delete_expired(ttl_hours)

    @staticmethod
    @contextmanager
    def _search_executor(max_workers=8):
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="search_orch")
        try:
            yield executor
        finally:
            executor.shutdown(wait=False)
