"""订阅管理工具 handler"""

from app.agent.tools.base import ToolResult
from app.agent.tools.context import ToolContext
from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.media.metadata.gateway import MetadataContext
from app.media.metadata.registry import registry as metadata_registry
from app.services.subscription_intent import resolve_subscription


def _normalize_profile(provider: str, content_profile: str | None) -> str:
    profile = str(content_profile or "").strip()
    if profile and profile != "default":
        return profile
    item = metadata_registry.get_provider(provider) if provider else None
    descriptor = getattr(item, "descriptor", None)
    profiles = {
        str(item)
        for item in getattr(descriptor, "content_profiles", frozenset())
        if str(item) and str(item) != "default"
    }
    return sorted(profiles)[0] if profiles else "default"


def _filter_profile(items: dict, content_profile: str | None) -> dict:
    profile = str(content_profile or "").strip()
    if not profile:
        return items
    if profile == "default":
        return {
            key: value
            for key, value in items.items()
            if not isinstance(value, dict) or (value.get("content_profile") or "default") == "default"
        }
    return {
        key: value
        for key, value in items.items()
        if isinstance(value, dict) and (value.get("content_profile") or "default") == profile
    }


def _code_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _resolve_aggregate_ref(
    ctx: ToolContext,
    provider: str,
    title: str,
    external_id: str,
    content_id: str,
    mtype: MediaType,
    profile: str,
    allow_private: bool,
    permissions: set[str],
) -> tuple[str, str, str]:
    """把虚拟聚合来源解析成具体 provider，并带回真实海报；找不到时保持原值."""
    metadata_gateway = getattr(ctx, "metadata_gateway", None)
    metadata = metadata_gateway or getattr(ctx, "metadata_service", None)
    if metadata is None:
        return provider, external_id, ""
    query = content_id or external_id or title
    try:
        if metadata_gateway is not None:
            hits = metadata_gateway.search(
                query=query,
                context=MetadataContext(
                    permissions=frozenset(permissions or ()),
                    content_profile=profile,
                    purpose="agent.subscribe",
                    allow_private=allow_private,
                ),
                provider=provider or None,
                media_type=mtype,
                content_profile=profile,
                limit=10,
            )
        else:
            hits = metadata.search(
                query=query,
                provider=provider or None,
                media_type=mtype,
                content_profile=profile,
                limit=10,
                allow_private=allow_private,
                permissions=permissions,
            )
    except Exception:  # noqa: BLE001 - 搜索失败不阻断订阅
        return provider, external_id, ""
    target = _code_key(query)
    for hit in hits or []:
        ref = hit.get("ref") or {}
        hit_provider = str(ref.get("provider") or hit.get("provider") or "").strip()
        hit_external = str(ref.get("external_id") or "").strip()
        if not hit_provider or not hit_external or hit_provider == "content_id":
            continue
        hit_title = _code_key(str(hit.get("title") or ""))
        if target and target not in hit_title:
            continue
        return hit_provider, hit_external, str(hit.get("poster") or "")
    return provider, external_id, ""


def subscribe_add(
    ctx: ToolContext,
    title: str,
    media_type: str = "movie",
    year: int | None = None,
    season: int | None = None,
    user_id: str | None = None,
    provider: str | None = None,
    external_id: str | None = None,
    content_id: str | None = None,
    metadata_ref: str | None = None,
    content_profile: str | None = None,
    metadata_policy: str | None = None,
) -> ToolResult:
    provider = str(provider or "").strip().lower()
    external_id = str(external_id or "").strip()
    content_id = str(content_id or "").strip()
    ref = str(metadata_ref or "").strip()
    if not provider and ref and ":" in ref:
        provider, external_id = ref.split(":", 1)
    elif provider and external_id:
        ref = f"{provider}:{external_id}"

    profile = _normalize_profile(provider, content_profile)
    if profile != "default" and not provider:
        return ToolResult(success=False, error="非默认内容画像必须指定 provider")

    mtype = MediaType.MOVIE if profile != "default" or media_type == "movie" else MediaType.TV
    user = ctx.user_context(user_id)
    permissions = set(getattr(user, "permissions", []) or [])
    allow_private = bool(user and (getattr(user, "is_superadmin", False) or "metadata:private:view" in permissions))
    descriptor = getattr(metadata_registry.get_provider(provider), "descriptor", None) if provider else None
    private_profile = profile not in ("", "default", "anime")
    if (getattr(descriptor, "visibility", "public") == "private" or private_profile) and not allow_private:
        return ToolResult(success=False, error="当前用户无 metadata:private:view 权限")

    # 聚合 Provider 只负责元数据合成，不应作为订阅来源落库：
    # 先按番号解析到真实 provider，并带回海报供通知/列表使用。
    poster = ""
    is_virtual = bool(getattr(descriptor, "virtual", False))
    if is_virtual:
        requested_provider = provider
        provider, external_id, poster = _resolve_aggregate_ref(
            ctx,
            provider,
            title,
            external_id,
            content_id,
            mtype,
            profile,
            allow_private,
            permissions,
        )
        if provider == requested_provider:
            return ToolResult(
                success=False,
                error=f"未找到 {content_id or title} 的真实元数据来源，未创建订阅",
            )
        if provider and external_id:
            ref = f"{provider}:{external_id}"

    # 只给来源没给 detail id 时，先用元数据搜索解析到具体 provider ref
    if provider and not external_id and not ref:
        metadata_gateway = getattr(ctx, "metadata_gateway", None)
        metadata = metadata_gateway or getattr(ctx, "metadata_service", None)
        if metadata is None:
            return ToolResult(success=False, error="缺少 external_id，且元数据服务不可用")
        try:
            if metadata_gateway is not None:
                hits = metadata_gateway.search(
                    query=title,
                    context=MetadataContext(
                        permissions=frozenset(permissions or ()),
                        content_profile=profile,
                        purpose="agent.subscribe",
                        allow_private=allow_private,
                    ),
                    provider=provider,
                    media_type=mtype,
                    content_profile=profile,
                    limit=5,
                )
            else:
                hits = metadata.search(
                    query=title,
                    provider=provider,
                    media_type=mtype,
                    content_profile=profile,
                    limit=5,
                    allow_private=allow_private,
                    permissions=permissions,
                )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"元数据搜索失败: {exc}")
        if not hits:
            return ToolResult(success=False, error=f"未找到 {provider} 来源: {title}")
        ref_obj = hits[0].get("ref") or {}
        external_id = str(ref_obj.get("external_id") or "").strip()
        if not external_id:
            return ToolResult(success=False, error=f"{provider} 搜索结果缺少 external_id")
        ref = f"{provider}:{external_id}"

    intent = resolve_subscription(
        provider,
        external_id,
        title,
        content_profile=content_profile,
        metadata_policy=metadata_policy,
    )
    if intent is None:
        return ToolResult(success=False, error=f"未注册的元数据来源: {provider}")
    keyword = content_id or intent.keyword
    code, msg, _ = ctx.subscribe_service.add_rss_subscribe(
        mtype=intent.media_type or mtype,
        name=title,
        year=str(year) if year else None,
        channel="auto",
        season=season,
        state="R",
        in_from=SearchType.API,
        user_id=int(user_id) if user_id and str(user_id).isdigit() else None,
        metadata_ref=intent.metadata_ref,
        metadata_policy=intent.metadata_policy,
        content_profile=intent.content_profile,
        keyword=keyword,
        mediaid=intent.mediaid,
        image=poster or None,
        allow_private=intent.allow_private or allow_private,
        permissions=permissions,
    )
    if code == 0:
        return ToolResult(
            success=True,
            data={
                "title": title,
                "content_profile": profile,
                "provider": provider or None,
                "image": poster or None,
                "message": msg or "订阅成功",
            },
        )
    return ToolResult(success=False, error=msg or "订阅失败")


def subscribe_list(
    ctx: ToolContext,
    media_type: str | None = None,
    content_profile: str | None = None,
    user_id: str | None = None,
) -> ToolResult:
    user = ctx.user_context(user_id)
    data: dict = {}
    if media_type in (None, "movie"):
        data["movies"] = _filter_profile(
            ctx.subscribe_service.get_subscribe_movies(user=user) or {},
            content_profile,
        )
    if media_type in (None, "tv"):
        data["tvs"] = _filter_profile(
            ctx.subscribe_service.get_subscribe_tvs(user=user) or {},
            content_profile,
        )
    return ToolResult(success=True, data=data)


def subscribe_delete(
    ctx: ToolContext, sub_id: int, media_type: str = "movie", user_id: str | None = None
) -> ToolResult:
    mtype = MediaType.MOVIE if media_type == "movie" else MediaType.TV
    ctx.subscribe_service.cancel_subscribe(mtype=mtype, rssid=sub_id, user=ctx.user_context(user_id))
    return ToolResult(success=True, data={"sub_id": sub_id, "deleted": True})


def subscribe_detail(
    ctx: ToolContext,
    title: str,
    tmdb_id: int | None = None,
    media_type: str | None = None,
    content_profile: str | None = None,
    user_id: str | None = None,
) -> ToolResult:
    """查询单个订阅详情；默认同时查电影和剧集."""
    user = ctx.user_context(user_id)
    try:
        items: list = []
        if media_type in (None, "movie"):
            get_movies = getattr(ctx.subscribe_service, "get_subscribe_movies", None)
            if get_movies:
                movies = get_movies(user=user) or {}
                items.extend(movies.values() if isinstance(movies, dict) else movies)
        if media_type in (None, "tv"):
            get_tvs = getattr(ctx.subscribe_service, "get_subscribe_tvs", None)
            if get_tvs:
                tvs = get_tvs(user=user) or {}
                items.extend(tvs.values() if isinstance(tvs, dict) else tvs)
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"查询订阅详情失败: {e}")
    keyword = (title or "").strip().lower()
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if content_profile and (item.get("content_profile") or "default") != content_profile:
            continue
        name = str(item.get("name") or "").lower()
        try:
            item_tmdb_id = int(item.get("tmdbid") or 0)
        except (TypeError, ValueError):
            item_tmdb_id = 0
        if (keyword and keyword in name) or (tmdb_id and item_tmdb_id == int(tmdb_id)):
            found.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "year": item.get("year"),
                    "season": item.get("season"),
                    "tmdb_id": item.get("tmdbid"),
                    "content_profile": item.get("content_profile"),
                    "anchor_provider": item.get("anchor_provider"),
                    "anchor_external_id": item.get("anchor_external_id"),
                    "total": item.get("total"),
                    "lack": item.get("lack"),
                    "total_ep": item.get("total_ep"),
                    "current_ep": item.get("current_ep"),
                    "state": item.get("state"),
                    "rss_sites": item.get("rss_sites"),
                    "search_sites": item.get("search_sites"),
                    "keyword": item.get("keyword"),
                }
            )
    if not found:
        return ToolResult(success=False, error=f"未找到订阅: {title}")
    return ToolResult(success=True, data={"total": len(found), "items": found})
