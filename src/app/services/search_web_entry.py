"""Web 搜索统一入口 — 构建 SearchContext 走 SearchOrchestrator

替代已删除的 search_web_service.search_medias_for_web（294 行重复流水线）。
Web 特有逻辑（默认订阅站点、tmdbid 直达）在此收敛，orchestrator 保持通用。
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

import log
from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.media import meta_info
from app.services.search_context import SearchContext
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_subject import SearchSubject
from app.services.subscribe.default_settings import get_default_setting

# 锚点元数据只是资源搜索的辅助信息；外部源不可用时必须尽快回退关键词，
# 不能因为一次详情抓取把整次搜索拖在 0%。
ANCHOR_RESOLVE_TIMEOUT = 15.0


def _resolve_anchor_with_timeout(fn, *args, timeout: float = ANCHOR_RESOLVE_TIMEOUT, **kwargs):
    """在独立线程内解析锚点，超时/异常一律返回 None 交给调用方回退."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anchor_resolve")
    future = executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        log.warn(f"[Orchestrator]锚点元数据解析超过 {timeout:.0f}s，回退关键词搜索")
        return None
    except Exception as exc:  # noqa: BLE001 - 元数据失败不应中断资源搜索
        log.warn(f"[Orchestrator]锚点元数据解析失败: {exc}")
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def make_web_search_fn(orchestrator: SearchOrchestrator, system_config: Any):
    """生成 WebSearchService 所需的 search_fn（签名与旧流水线一致）"""

    def _search_impl(
        content: str,
        ident_flag: bool = True,
        filters: dict | None = None,
        metadata_ref: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        identity_id: str | None = None,
        content_profile: str | None = None,
        media_type: MediaType | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
    ) -> tuple[int, str]:
        # 前端可能把未选择的类型序列化为空串；空串进入 SearchQuery 会触发枚举校验失败，
        # 导致锚点元数据在发起请求前就被判失败。此处统一归一为 None。
        media_type = media_type or None
        filter_args = dict(filters or {})
        if content_profile:
            filter_args["content_profile"] = content_profile
        if anchor_provider:
            filter_args["anchor_provider"] = anchor_provider
        if anchor_external_id:
            filter_args["anchor_external_id"] = anchor_external_id
        if identity_id:
            filter_args["identity_id"] = identity_id
        if metadata_ref:
            filter_args["metadata_ref"] = metadata_ref

        requested_rule = filter_args.get("rule")
        profile = str(filter_args.get("content_profile") or "").strip()
        subject = SearchSubject.classify(
            media_type,
            profile,
            anchor_provider,
            anchor_external_id or metadata_ref or filter_args.get("tmdbid"),
        )
        lookup_type = subject.provider_type or media_type
        media_type = lookup_type
        match_media = None
        resolve_provider = ""
        if anchor_provider and anchor_external_id:
            resolve_provider = anchor_provider
            if anchor_provider == "content_id":
                # content_id 是内部锚点，没有对应 metadata provider。
                # 用页面选定的真实来源解析编号，再还原 content_id 身份。
                resolve_provider = str(filter_args.get("metadata_source") or "").strip()
                if resolve_provider == "content_id":
                    resolve_provider = ""
            resolved_profile = content_profile or str(filter_args.get("content_profile") or "default")
            if anchor_provider == "content_id":
                match_media = _resolve_anchor_with_timeout(
                    orchestrator.resolve_content_id_media,
                    resolve_provider,
                    str(anchor_external_id),
                    media_type=lookup_type,
                    content_profile=resolved_profile,
                    timeout=45.0,
                )
                if match_media:
                    match_media.anchor_provider = anchor_provider
                    match_media.anchor_external_id = str(anchor_external_id)
                    if identity_id:
                        match_media.identity_id = identity_id
            else:
                match_media = _resolve_anchor_with_timeout(
                    orchestrator.resolve_anchor_media,
                    resolve_provider,
                    str(anchor_external_id),
                    media_type=lookup_type,
                    content_profile=resolved_profile,
                )
            if not match_media:
                if anchor_provider == "content_id":
                    # 编号锚点只是内部定位；元数据源临时熔断/限流时仍应能按编号搜资源。
                    log.warn(
                        f"[Orchestrator]编号锚点解析失败 {anchor_provider}:{anchor_external_id}，"
                        f"回退关键词搜索: {content}"
                    )
                else:
                    return -1, f"{content} 未识别到媒体信息！"
            if anchor_provider not in ("content_id", profile) and not orchestrator.identity_matches_keyword(
                match_media, content
            ):
                # 前端路由可能残留上一次搜索的锚点（例如同编号的电影/剧集），
                # 与当前关键词不一致时必须丢弃，否则会继续用错误身份搜索。
                log.warn(
                    f"[Orchestrator]忽略不匹配锚点 {anchor_provider}:{anchor_external_id}，改按关键词识别: {content}"
                )
                match_media = None
                for key in ("anchor_provider", "anchor_external_id", "identity_id", "metadata_ref"):
                    filter_args.pop(key, None)

        if match_media is None and profile and profile != "default":
            # 无 TMDB ID 的来源仍需一个本地匹配目标；content_id 未知类型时不硬编码电影。
            match_media = meta_info(title=content, mtype=lookup_type)
            match_media.content_profile = profile
            match_media.keyword = content
            if lookup_type:
                match_media.type = lookup_type
            match_media.anchor_provider = str(
                filter_args.get("anchor_provider") or filter_args.get("metadata_source") or profile
            )
            match_media.anchor_external_id = str(filter_args.get("anchor_external_id") or content)
            fallback_provider = str(
                resolve_provider or filter_args.get("metadata_source") or match_media.anchor_provider or ""
            ).strip()
            if fallback_provider and fallback_provider not in ("content_id", profile):
                # 编号解析失败时仍保留真实搜索来源，避免通知里出现内部伪 provider。
                match_media.provider = fallback_provider
                match_media.metadata_ref = f"{fallback_provider}:{match_media.anchor_external_id}"
            if not match_media.get_name():
                match_media.en_name = content
            # 自定义画像的编号不能走 TMDB 识别，避免错误映射导致资源过滤失败。
            ident_flag = False
        # 结果过滤器按提供方类型判断资源形态：动漫在资源侧仍按电视（Sxx/集数）过滤。
        # 展示/入库类型单独保留 ANIME，避免两者互相覆盖后电影资源混入动漫搜索。
        candidate_type = subject.provider_type or filter_args.get("type") or lookup_type
        if not candidate_type and match_media is not None:
            candidate_type = match_media.type
        if isinstance(candidate_type, str):
            candidate_type = MediaType.from_string(candidate_type)
        if candidate_type == MediaType.UNKNOWN:
            candidate_type = None
        display_type = subject.display_type or candidate_type
        if candidate_type:
            filter_args["type"] = candidate_type
        if match_media is not None and display_type and match_media.type != display_type:
            # 搜索主体只有一种真实类型；锚点缺类型时按主体类型修正。
            match_media.type = display_type
        if (
            candidate_type == MediaType.MOVIE
            and match_media is not None
            and str(getattr(match_media, "year", "") or "").isdigit()
            and int(str(match_media.year)) > 0
        ):
            # 电影搜索用身份年份收敛同系列的不同作品，避免“生化危机2”混进 2026 新片。
            if not str(filter_args.get("year") or "").strip():
                filter_args["year"] = str(match_media.year)

        # 探索/订阅来源：站点优先级 = 订阅默认设置 → 页面选择的搜索站点 → 全部站点
        site_fallback = filter_args.pop("site_fallback", None)
        default_site_first = bool(filter_args.pop("site_default_first", None))
        if filter_args.get("site") == []:
            # 显式选择「全部已授权站点」：归一为 None（全部可见站点）
            filter_args["site"] = None
        if system_config:
            if "site" not in filter_args:
                _apply_default_sites(
                    filter_args,
                    media_type,
                    system_config,
                    profile,
                    site_fallback,
                    default_first=default_site_first,
                    user_id=user_id,
                )
            else:
                # 站点已经由前端指定/归一为全部时，仍要继承默认过滤规则。
                _apply_default_rule(filter_args, media_type, system_config, profile, user_id)

        if requested_rule in (None, ""):
            # 手动资源搜索不默认套用中字规则组；用户显式选择规则时仍生效。
            filter_args["rule"] = -1

        ctx = SearchContext(
            keyword=content,
            session_id=session_id or "web",
            search_type=SearchType.WEB,
            match_media=match_media,
            media_type=lookup_type,
            ident_flag=ident_flag,
            filter_args=filter_args,
            auto_download=False,
            persist=True,
            user_id=str(user_id) if user_id else None,
        )
        _, _, total, _ = orchestrator.orchestrate(ctx)
        if total:
            return 0, ""
        return 1, f"{content} 未搜索到任何资源"

    def search_fn(content: str, **kwargs: Any) -> tuple[int, str]:
        """所有资源搜索都先建立进度：锚点解析可能慢，但前端不能停在 0%."""
        session_id = str(kwargs.get("session_id") or "web")
        orchestrator.begin_search(session_id, content)
        try:
            return _search_impl(content, **kwargs)
        finally:
            orchestrator.end_search(session_id)

    return search_fn


def _default_subscribe_setting(
    media_type: MediaType | None,
    system_config: Any,
    content_profile: str | None = None,
    user_id: int | str | None = None,
) -> dict:
    return get_default_setting(system_config, media_type, content_profile, user_id)


def _apply_default_rule(
    filter_args: dict,
    media_type: MediaType | None,
    system_config: Any,
    content_profile: str | None = None,
    user_id: int | str | None = None,
) -> None:
    """站点已指定时仍继承默认订阅的过滤规则."""
    default_setting = _default_subscribe_setting(media_type, system_config, content_profile, user_id)
    if not filter_args.get("rule") and default_setting.get("rule") not in (None, ""):
        filter_args["rule"] = default_setting.get("rule")


def _apply_default_sites(
    filter_args: dict,
    media_type: MediaType | None,
    system_config: Any,
    content_profile: str | None = None,
    fallback_sites: list[str] | None = None,
    default_first: bool = False,
    user_id: int | str | None = None,
) -> None:
    """探索/订阅搜索：订阅默认站点 + 页面选择站点合并，默认站点优先；都为空则全部可见."""
    try:
        default_setting = _default_subscribe_setting(media_type, system_config, content_profile, user_id)
        default_sites = list(default_setting.get("search_sites") or [])
        resolved = list(default_sites)
        for site in fallback_sites or []:
            if site not in resolved:
                resolved.append(site)
        if default_first and default_sites:
            # 真正的搜索 tier：默认站点整体高于补充站点，不被更高的全局优先级压过。
            filter_args["site_tier"] = default_sites
        # None = 不限制，由索引器按用户可见站点过滤；避免空列表被当成"零站点"
        filter_args["site"] = resolved or None
        # 资源搜索沿用默认订阅的过滤规则，不静默退回全局默认组。
        if not filter_args.get("rule") and default_setting.get("rule") not in (None, ""):
            filter_args["rule"] = default_setting.get("rule")
    except Exception as e:
        log.warn(f"[WebSearch]读取默认订阅设置站点失败: {e}")
