"""Subscribe update service - 更新订阅."""

from dataclasses import asdict
from typing import Any, cast

import log
from app.domain.entities.rss import SubscribeState
from app.domain.enums import SubscribeType
from app.domain.media_types import ProviderMediaType
from app.events import Event
from app.events.constants import SUBSCRIBE_ADD
from app.events.payloads import SubscribeAddPayload
from app.media import meta_info
from app.media.display_image_policy import unwrap_display_image_url
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.schemas.auth import UserContext
from app.services.subscribe.management.utils import gen_rss_note
from app.services.web.utils import WebUtils


class SubscribeUpdateService:
    """更新订阅服务"""

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        movie_repo,
        tv_repo,
        media_service,
        message,
        event_bus,
        system_config,
        web_utils: WebUtils,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._media = media_service
        self._message = message
        self._event_bus = event_bus
        self._system_config = system_config
        self._web_utils = web_utils
        self._metadata_gateway = metadata_gateway

    @staticmethod
    def _text(row, name: str) -> str:
        value = getattr(row, name, "")
        return value.strip() if isinstance(value, str) else ""

    @classmethod
    def _is_generic_subscription(cls, row) -> bool:
        anchor_provider = cls._text(row, "ANCHOR_PROVIDER")
        profile = cls._text(row, "CONTENT_PROFILE")
        tmdbid = cls._text(row, "TMDBID")
        source_provider = cls._text(row, "PROVIDER")
        metadata_ref = cls._text(row, "METADATA_REF")
        return bool(
            (anchor_provider and anchor_provider != "tmdb")
            or (profile and profile != "default")
            or (source_provider and source_provider != "tmdb")
            or (metadata_ref and not metadata_ref.startswith("tmdb:"))
            or (not tmdbid)
        )

    @staticmethod
    def _existing(row, *names, default=None):
        for name in names:
            value = getattr(row, name, None)
            if value is not None:
                return value
        return default

    def _update_generic(
        self,
        repo,
        row,
        *,
        mtype,
        rssid,
        name,
        year,
        keyword,
        season,
        image,
        over_edition,
        filter_restype,
        filter_pix,
        filter_team,
        filter_rule,
        filter_include,
        filter_exclude,
        filter_free,
        save_path,
        download_setting,
        total_ep,
        current_ep,
        state,
        rss_sites,
        search_sites,
        user,
        content_profile=None,
        provider=None,
        metadata_ref=None,
        metadata_policy=None,
        naming_profile=None,
    ):
        title = str(name or self._existing(row, "NAME", "name", default="") or "")
        resolved_year = str(year or self._existing(row, "YEAR", "year", default="") or "")
        anchor_provider = self._existing(row, "ANCHOR_PROVIDER", "anchor_provider")
        external = self._existing(row, "ANCHOR_EXTERNAL_ID", "anchor_external_id")
        if str(external or "").startswith("content_id:"):
            anchor_provider = "content_id"
            external = str(external).split(":", 1)[1]
        profile = content_profile or self._existing(row, "CONTENT_PROFILE", "content_profile")
        identity_id = self._existing(row, "IDENTITY_ID", "identity_id")
        # 参数 provider 是元数据来源；锚点 provider 独立保存，不能混用。
        source_provider = provider or self._existing(row, "PROVIDER", "provider")
        source_ref = metadata_ref or self._existing(row, "METADATA_REF", "metadata_ref")
        policy = metadata_policy or self._existing(row, "METADATA_POLICY", "metadata_policy")
        naming = naming_profile or self._existing(row, "NAMING_PROFILE", "naming_profile")
        current_keyword = str(self._existing(row, "KEYWORD", "keyword", default="") or "")
        if current_keyword.startswith("content_id:"):
            current_keyword = current_keyword.split(":", 1)[1]
        if keyword and str(keyword).startswith("content_id:"):
            keyword = str(keyword).split(":", 1)[1]
        values = {
            "name": title,
            "year": resolved_year,
            "keyword": keyword or current_keyword,
            "image": image or self._existing(row, "IMAGE", "image", default=""),
            "tmdbid": (
                self._existing(row, "TMDBID", "tmdbid", default="") if str(anchor_provider or "tmdb") == "tmdb" else ""
            ),
            "identity_id": identity_id,
            "anchor_provider": anchor_provider,
            "anchor_external_id": external,
            "content_profile": profile,
            "provider": source_provider,
            "metadata_ref": source_ref,
            "metadata_policy": policy,
            "naming_profile": naming,
            "over_edition": over_edition,
            "filter_restype": filter_restype,
            "filter_pix": filter_pix,
            "filter_team": filter_team,
            "filter_rule": filter_rule,
            "filter_include": filter_include,
            "filter_exclude": filter_exclude,
            "filter_free": filter_free,
            "save_path": save_path,
            "download_setting": download_setting,
            "state": state or self._existing(row, "STATE", "state", default="R"),
            "rss_sites": rss_sites,
            "search_sites": search_sites,
        }
        if mtype != ProviderMediaType.MOVIE:
            values.update(
                {
                    "season": season or self._existing(row, "SEASON", "season", default=""),
                    "total": self._existing(row, "TOTAL", "total", default=0),
                    "lack": self._existing(row, "LACK", "lack", default=0),
                    "total_ep": total_ep if total_ep is not None else self._existing(row, "TOTAL_EP", "total_ep"),
                    "current_ep": current_ep
                    if current_ep is not None
                    else self._existing(row, "CURRENT_EP", "current_ep"),
                }
            )
        code = repo.update(rssid=rssid, user=user, **values)
        media_info = meta_info(title=title, mtype=mtype)
        media_info.title = title
        media_info.year = resolved_year
        media_info.type = mtype
        media_info.poster_path = values["image"]
        media_info.anchor_provider = anchor_provider
        media_info.anchor_external_id = external
        media_info.identity_id = identity_id
        media_info.content_profile = str(profile or "default")
        media_info.provider = source_provider
        media_info.metadata_ref = source_ref
        media_info.keyword = values["keyword"]
        return code, "更新成功" if code == 0 else "更新失败", media_info

    def _season_episode_count(
        self,
        *,
        media_info: Any,
        title: str,
        year: str | None,
        media_type: ProviderMediaType,
        season: int,
        content_profile: str,
        provider_data: dict[str, Any] | None,
    ) -> int:
        if self._metadata_gateway is None:
            return 0
        provider = str(getattr(media_info, "anchor_provider", "") or "tmdb")
        external_id = str(getattr(media_info, "anchor_external_id", "") or getattr(media_info, "tmdb_id", "") or "")
        return self._metadata_gateway.resolve_season_episode_count(
            context=MetadataContext(
                content_profile=content_profile,
                purpose="subscribe.update",
                allow_private=True,
            ),
            provider=provider,
            external_id=external_id,
            title=title,
            year=year,
            media_type=media_type,
            season=season,
            content_profile=content_profile,
            provider_data=provider_data,
        )

    def _resolve_existing_source(
        self,
        row,
        mtype,
        mediaid: str | None,
        metadata_ref: str | None,
        provider: str | None,
    ):
        """按订阅自身来源解析元数据：TMDB 走 TMDB，豆瓣/插件走各自 provider."""
        ref = ""
        if mediaid and ":" in str(mediaid):
            ref = str(mediaid)
        elif metadata_ref and ":" in str(metadata_ref):
            ref = str(metadata_ref)
        else:
            source_provider = str(provider or self._text(row, "PROVIDER") or "").strip().lower()
            external = self._text(row, "ANCHOR_EXTERNAL_ID")
            if source_provider and external:
                ref = f"{source_provider}:{external}"
        if not ref or ref.lower().startswith("tmdb:"):
            return None
        try:
            return self._web_utils.get_mediainfo_from_id(mtype=mtype, mediaid=ref)
        except Exception as exc:  # noqa: BLE001 - 元数据源失败时仍允许保存
            log.warn(f"[Subscribe]按来源 {ref} 解析元数据失败，使用现有字段保存: {exc}")
            return None

    def update_rss_subscribe(
        self,
        mtype: Any,
        rssid: int | None,
        name: str | None = None,
        year: Any = None,
        keyword: str | None = None,
        season: int | None = None,
        fuzzy_match: bool = False,
        mediaid: str | None = None,
        rss_sites: list[str] | str | None = None,
        search_sites: list[str] | str | None = None,
        over_edition: bool | int = False,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        filter_free: bool | None = None,
        save_path: str | None = None,
        download_setting: int | str | None = None,
        total_ep: int | None = None,
        current_ep: int | None = None,
        state: str | None = None,
        in_from: str | None = None,
        user_name: str | None = None,
        image: str | None = None,
        user: UserContext | None = None,
        provider: str | None = None,
        metadata_ref: str | None = None,
        content_profile: str | None = None,
        metadata_policy: str | None = None,
        naming_profile: str | None = None,
    ) -> tuple[int, str, Any]:
        """更新电影、电视剧订阅（user 非空且非超管时仅可更新自己的订阅）"""
        if not rssid:
            return -1, "缺少订阅ID", None
        if image:
            image = unwrap_display_image_url(image)

        # 归属校验：普通用户越权更新返回不存在（避免资源探测）
        if user is not None and not user.is_superadmin:
            owner_repo = self._movie_repo if mtype == ProviderMediaType.MOVIE else self._tv_repo
            if not owner_repo.get_all(rssid=int(rssid), user=user):
                return -1, "订阅不存在", None

        year = int(str(year)) if str(year).isdigit() else ""
        if isinstance(rss_sites, str):
            rss_sites = rss_sites.split(",")
        if isinstance(search_sites, str):
            search_sites = search_sites.split(",")
        over_edition = 1 if over_edition else 0
        filter_rule = int(str(filter_rule)) if str(filter_rule).isdigit() else 0
        total_ep = int(str(total_ep)) if str(total_ep).isdigit() else None
        current_ep = int(str(current_ep)) if str(current_ep).isdigit() else None
        download_setting = int(str(download_setting)) if str(download_setting).replace("-", "").isdigit() else -1
        fuzzy_match = bool(fuzzy_match)

        repo = self._movie_repo if mtype == ProviderMediaType.MOVIE else self._tv_repo
        existing_rows = repo.get_all(rssid=int(rssid), user=user)
        existing = existing_rows[0] if existing_rows else None
        effective_state = state or (
            self._existing(existing, "STATE", "state", default=SubscribeState.PENDING.value)
            if existing is not None
            else SubscribeState.PENDING.value
        )
        generic_kwargs = {
            "mtype": mtype,
            "rssid": int(rssid),
            "name": name,
            "year": year,
            "keyword": keyword,
            "season": season,
            "image": image,
            "over_edition": over_edition,
            "filter_restype": filter_restype,
            "filter_pix": filter_pix,
            "filter_team": filter_team,
            "filter_rule": filter_rule,
            "filter_include": filter_include,
            "filter_exclude": filter_exclude,
            "filter_free": filter_free,
            "save_path": save_path,
            "download_setting": download_setting,
            "total_ep": total_ep,
            "current_ep": current_ep,
            "state": effective_state,
            "rss_sites": rss_sites,
            "search_sites": search_sites,
            "user": user,
            "content_profile": content_profile,
            "provider": provider,
            "metadata_ref": metadata_ref,
            "metadata_policy": metadata_policy,
            "naming_profile": naming_profile,
        }
        if existing is not None and self._is_generic_subscription(existing):
            resolved = self._resolve_existing_source(existing, mtype, mediaid, metadata_ref, provider)
            if resolved is not None:
                # 用户显式填写的字段优先，其余用来源自身的最新元数据补齐。
                generic_kwargs["name"] = name or resolved.title
                generic_kwargs["year"] = year or resolved.year
                if not image:
                    generic_kwargs["image"] = resolved.get_poster_image() or generic_kwargs["image"]
            return self._update_generic(repo, existing, **generic_kwargs)

        media_info = None
        if not fuzzy_match:
            if mediaid:
                media_info = self._web_utils.get_mediainfo_from_id(mtype=mtype, mediaid=mediaid)
                if not season and media_info:
                    season = media_info.begin_season
            else:
                if season:
                    title = "%s %s 第%s季".strip() % (name, year, season)
                else:
                    title = "%s %s".strip() % (name, year)
                media_info = (
                    self._metadata_gateway.resolve_by_title(
                        title=title,
                        media_type=mtype,
                        year=str(year or "") or None,
                        strict=bool(year),
                        cache=False,
                        context=MetadataContext(
                            content_profile=str(content_profile or "default"),
                            purpose="subscribe.update",
                            allow_private=True,
                        ),
                    )
                    if self._metadata_gateway is not None
                    else None
                )
            if not media_info or not media_info.provider_data:
                if existing is not None:
                    # 编辑已有订阅不应依赖 TMDB 可用性：保留原锚点/身份并保存可编辑字段。
                    log.warn(f"[Subscribe]更新时 TMDB 查询失败，使用现有订阅身份保存: {name} ({year})")
                    return self._update_generic(repo, existing, **generic_kwargs)
                return 1, "TMDB无法查询到媒体信息", None
            if media_info.type != ProviderMediaType.MOVIE:
                if not season and str(mediaid).startswith("DB:"):
                    season = 1
                if season:
                    total_episode = total_ep or self._season_episode_count(
                        media_info=media_info,
                        title=str(name or media_info.title or ""),
                        year=str(media_info.year or year or "") or None,
                        media_type=mtype,
                        season=int(season),
                        content_profile=str(content_profile or "default"),
                        provider_data=media_info.provider_data,
                    )
                else:
                    total_seasoninfo = (
                        self._metadata_gateway.season_summaries(media_info.provider_data)
                        if self._metadata_gateway is not None
                        else []
                    )
                    if not total_seasoninfo:
                        return 2, "获取剧集信息失败", media_info
                    total_seasoninfo = sorted(
                        total_seasoninfo, key=lambda x: int(x.get("season_number") or 0), reverse=True
                    )
                    season = total_seasoninfo[0].get("season_number")
                    total_episode = total_seasoninfo[0].get("episode_count")
                if not total_episode:
                    return 3, f"第{season}季获取剧集数失败，请确认该季是否存在", media_info
                media_info.begin_season = int(season or 0)
                media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                if current_ep:
                    # 首个待下载集为 current_ep → 缺失集数 = total - current_ep + 1
                    lack = max(0, total - current_ep + 1)
                else:
                    lack = total
                season_str = media_info.get_season_string()
                code = self._tv_repo.update(
                    rssid=int(rssid),
                    user=user,
                    name=media_info.title,
                    year=media_info.year,
                    season=season_str,
                    tmdbid=media_info.tmdb_id,
                    image=image or media_info.get_poster_image(),
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    filter_free=filter_free,
                    save_path=save_path,
                    download_setting=download_setting,
                    total_ep=total_ep,
                    current_ep=current_ep,
                    total=total,
                    lack=lack,
                    state=effective_state,
                    desc=media_info.overview,
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                    fuzzy_match=0,
                    provider=provider,
                    metadata_ref=metadata_ref,
                    content_profile=content_profile,
                    metadata_policy=metadata_policy,
                    naming_profile=naming_profile,
                )
            else:
                code = self._movie_repo.update(
                    rssid=int(rssid),
                    user=user,
                    name=media_info.title,
                    year=media_info.year,
                    tmdbid=media_info.tmdb_id,
                    image=image or media_info.get_poster_image(),
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    filter_free=filter_free,
                    save_path=save_path,
                    download_setting=download_setting,
                    state=effective_state,
                    desc=media_info.overview,
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                    fuzzy_match=0,
                    provider=provider,
                    metadata_ref=metadata_ref,
                    content_profile=content_profile,
                    metadata_policy=metadata_policy,
                    naming_profile=naming_profile,
                )
        else:
            media_info = meta_info(title=name or "", mtype=mtype)
            media_info.title = name
            media_info.type = mtype
            if season:
                media_info.begin_season = int(season)
            if mtype == ProviderMediaType.MOVIE:
                code = self._movie_repo.update(
                    rssid=int(rssid),
                    user=user,
                    name=name,
                    year=year,
                    image=image,
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    filter_free=filter_free,
                    save_path=save_path,
                    download_setting=download_setting,
                    state=effective_state,
                    keyword=keyword,
                    fuzzy_match=1,
                )
            else:
                season_str = media_info.get_season_string() if media_info.begin_season else ""
                code = self._tv_repo.update(
                    rssid=int(rssid),
                    user=user,
                    name=name,
                    year=year,
                    season=season_str,
                    image=image,
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    filter_free=filter_free,
                    save_path=save_path,
                    download_setting=download_setting,
                    total=0,
                    lack=0,
                    state=effective_state,
                    keyword=keyword,
                    fuzzy_match=1,
                )

        if code == 0:
            self._event_bus.publish(
                Event(
                    event_type=SUBSCRIBE_ADD,
                    payload=asdict(
                        SubscribeAddPayload(
                            media=media_info.to_dict() if media_info else {},
                            rssid=rssid,
                            rss_sites=cast(list[str], rss_sites),
                            search_sites=cast(list[str], search_sites),
                            over_edition=bool(over_edition),
                            filter_restype=filter_restype,
                            filter_pix=filter_pix,
                            filter_team=filter_team,
                            filter_rule=filter_rule,
                            save_path=save_path,
                            download_setting=download_setting,
                            total_ep=total_ep,
                            current_ep=current_ep,
                            fuzzy_match=fuzzy_match,
                            keyword=keyword,
                        )
                    ),
                ),
            )
            if in_from and media_info:
                media_info.user_name = user_name
                media_info.user_id = user.user_id if user else None
                self._message.send_subscribe_success_message(
                    in_from=cast(SubscribeType, in_from), media_info=media_info
                )
            return code, "更新订阅成功", media_info
        else:
            return code, "更新订阅失败", media_info
