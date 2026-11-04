"""Subscribe add service - 添加订阅."""

from dataclasses import asdict
from typing import Any, cast

import log
from app.domain.entities.rss import SubscribeState
from app.domain.enums import SubscribeType, SystemConfigKey
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.constants import SUBSCRIBE_ADD
from app.events.payloads import SubscribeAddPayload
from app.media import meta_info
from app.media.display_image_policy import unwrap_display_image_url
from app.media.metadata import ProviderRef
from app.media.metadata.registry import registry as metadata_registry
from app.services.subscribe.management.utils import gen_rss_note
from app.services.web.utils import WebUtils


def _provider_is_virtual(provider: str) -> bool:
    desc = getattr(metadata_registry.get_provider(provider), "descriptor", None)
    return bool(getattr(desc, "virtual", False))


def _is_concrete_source(value: Any) -> bool:
    source = str(value or "").strip().lower()
    if not source or source in {"content_id", "unknown"}:
        return False
    return not _provider_is_virtual(source)


def _source_from_record(record: Any, provider: str) -> str:
    """从插件记录中选出真实来源：显式来源 > refs > provider 本身."""
    extra = getattr(record, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    value = extra.get("source_provider")
    if _is_concrete_source(value):
        return str(value).strip().lower()
    for ref in getattr(record, "refs", None) or []:
        value = getattr(ref, "provider", None)
        if _is_concrete_source(value):
            return str(value).strip().lower()
    return provider if _is_concrete_source(provider) else ""


def _resolve_provider_poster(provider: str, external_id: str, media_type: Any) -> tuple[str, str]:
    """从插件元数据解析真实海报和真实来源；失败时不使用 TMDB 占位图。"""
    obj = metadata_registry.get_provider(provider)
    detail = getattr(obj, "detail", None)
    if obj is None or not callable(detail):
        return "", ""
    try:
        record = detail(ProviderRef(provider=provider, external_id=external_id, media_type=media_type), None)
    except Exception:  # noqa: BLE001
        return "", ""
    if record is None:
        return "", ""
    posters = (getattr(record, "images", None) or {}).get("poster") or []
    poster = str(getattr(posters[0], "url", "") or "") if posters else ""
    source = _source_from_record(record, provider)
    if not source and posters:
        source = str(getattr(posters[0], "provider", "") or "")
    return poster, source


def _split_provider_ref(value: Any) -> tuple[str, str] | None:
    """拆分 `<provider>:<external_id>`，并归一化 DB/BG/TMDB 等旧前缀.

    以显式字面前缀为准；只有旧别名才映射到规范 provider key，
    避免 registry 的 ref_prefix 映射把插件 provider 误判成 tmdb/douban。
    """
    if value is None:
        return None
    text = str(value).strip()
    if ":" not in text:
        return None
    provider, external_id = text.split(":", 1)
    provider = provider.strip().lower()
    external_id = external_id.strip()
    if not provider or not external_id:
        return None
    aliases = {
        "db": "douban",
        "douban": "douban",
        "bgm": "bangumi",
        "bg": "bangumi",
        "bangumi": "bangumi",
        "tmdb": "tmdb",
    }
    return aliases.get(provider, provider), external_id


def _season_number(value, default: int = 0) -> int:
    text = str(value or "").strip()
    if text.upper().startswith("S"):
        text = text[1:]
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


class SubscribeAddService:
    """添加订阅服务"""

    def __init__(
        self,
        movie_repo,
        tv_repo,
        media_service,
        message,
        event_bus,
        system_config,
        web_utils: WebUtils,
        download_repo=None,
        transfer_history_manager=None,
        metadata_service=None,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._media = media_service
        self._message = message
        self._event_bus = event_bus
        self._system_config = system_config
        self._web_utils = web_utils
        self._download_repo = download_repo
        self._transfer_history_manager = transfer_history_manager
        self._metadata_service = metadata_service

    @property
    def default_subscribe_setting_tv(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultSubscribeSettingTV) or {}

    @property
    def default_subscribe_setting_mov(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultSubscribeSettingMovie) or {}

    def _identity_fields(
        self,
        media_info,
        mtype,
        mediaid=None,
        metadata_policy=None,
        content_profile=None,
        naming_profile=None,
    ) -> dict:
        if self._metadata_service is None:
            return {}
        return self._metadata_service.link_subscription(
            media_info,
            media_type=mtype,
            mediaid=mediaid,
            metadata_policy=metadata_policy,
            content_profile=content_profile,
            naming_profile=naming_profile,
        ).as_kwargs()

    def _provider_media_info(
        self,
        provider: str,
        external_id: str,
        *,
        name: str | None,
        year: Any,
        content_profile: str | None,
        allow_private: bool,
        permissions: set[str] | None,
        media_type: MediaType | None = None,
        season: int | None = None,
    ):
        """用插件 provider 的详情构造 MediaInfo，自定义画像不走 TMDB 查询."""
        if self._metadata_service is None:
            return None
        try:
            record = self._metadata_service.lookup(
                provider,
                external_id,
                media_type=media_type,
                content_profile=content_profile,
                allow_private=allow_private,
                permissions=permissions,
            )
        except Exception as exc:  # noqa: BLE001 - provider 失败回退旧查询
            log.warn(f"[SubscribeAdd] provider 详情查询失败 {provider}:{external_id}: {exc}")
            return None
        if not record:
            return None
        title = record.get("title") or name or external_id
        poster = record.get("poster")
        if not poster:
            images = record.get("images") or {}
            posters = images.get("poster") or []
            if posters:
                poster = posters[0].get("url")
        resolved_type = media_type or MediaType.from_string(str(record.get("media_type") or ""))
        if content_profile == "anime" or str(record.get("media_type") or "").lower() == "anime":
            resolved_type = MediaType.ANIME
        if resolved_type not in (MediaType.MOVIE, MediaType.TV, MediaType.ANIME):
            resolved_type = MediaType.MOVIE
        media_info = meta_info(title=title, mtype=resolved_type)
        media_info.title = title
        media_info.cn_name = title
        media_info.year = str(record.get("year") or year or "") or None
        media_info.poster_path = poster or ""
        actors = [
            str(item.get("name"))
            for item in (record.get("credits") or [])
            if isinstance(item, dict) and item.get("role") in ("actor", "actress") and item.get("name")
        ]
        overview = str(record.get("overview") or "").strip()
        if not overview and actors:
            overview = f"演员：{' / '.join(actors[:12])}"
        media_info.overview = overview
        media_info.type = resolved_type
        extra = record.get("extra") or {}
        season_number = _season_number(season, 1)
        total_episodes = (
            record.get("episode_count")
            or extra.get("bangumi.eps")
            or extra.get("douban.episodes_count")
            or extra.get("total_episodes")
        )
        for item in record.get("seasons") or []:
            if not isinstance(item, dict):
                continue
            if int(item.get("season_number") or -1) == season_number:
                total_episodes = item.get("episode_count") or total_episodes
                break
        if str(total_episodes or "").isdigit():
            media_info.total_episodes = int(str(total_episodes))
        media_info.begin_season = season_number
        media_info.content_profile = content_profile or record.get("content_profile") or "default"
        return media_info

    def _default_setting_for(self, mtype: Any, content_profile: str | None) -> dict:
        """按载体和内容画像读取默认订阅设置；画像配置为空时回退到载体默认."""
        if mtype in (MediaType.TV, MediaType.ANIME):
            return self.default_subscribe_setting_tv or {}
        profile = str(content_profile or "").strip()
        if profile and profile != "default":
            key = f"{SystemConfigKey.DefaultSubscribeSettingMovie.value}::{profile}"
            setting = self._system_config.get(key)
            if isinstance(setting, dict) and setting:
                return setting
        return self.default_subscribe_setting_mov or {}

    def add_rss_subscribe(
        self,
        mtype: Any,
        name: str | None,
        year: Any,
        channel: str | None = None,
        keyword: str | None = None,
        season: int | None = None,
        fuzzy_match: bool = False,
        mediaid: str | None = None,
        metadata_ref: str | None = None,
        provider: str | None = None,
        rss_sites: list[str] | str | None = None,
        search_sites: list[str] | str | None = None,
        # None = 未显式指定，新增时应用默认订阅设置的"洗版"；显式 True/False 以调用方为准
        over_edition: bool | int | None = None,
        filter_restype: str | None = None,
        filter_pix: str | None = None,
        filter_team: str | None = None,
        filter_rule: int | str | None = None,
        filter_include: str | None = None,
        filter_exclude: str | None = None,
        filter_free: bool | None = None,
        image: str | None = None,
        save_path: str | None = None,
        download_setting: int | str | None = None,
        total_ep: int | None = None,
        current_ep: int | None = None,
        state: str = SubscribeState.PENDING.value,
        rssid: int | None = None,
        in_from: str | None = None,
        user_name: str | None = None,
        user_id: int | None = None,
        metadata_policy: str | None = None,
        content_profile: str | None = None,
        naming_profile: str | None = None,
        allow_private: bool = False,
        permissions: set[str] | None = None,
    ) -> tuple[int, str, Any]:
        """添加电影、电视剧订阅（user_id 为订阅归属用户，None 为系统/插件创建）"""
        if not name:
            return -1, "标题或类型有误", None
        if image:
            image = unwrap_display_image_url(image)
        year = int(year) if str(year).isdigit() else ""

        # 新增订阅且未显式传值时，应用默认订阅设置
        if not rssid:
            default_rss_setting = self._default_setting_for(mtype, content_profile)
            if default_rss_setting:
                default_restype = default_rss_setting.get("restype")
                default_pix = default_rss_setting.get("pix")
                default_team = default_rss_setting.get("team")
                default_rule = default_rss_setting.get("rule")
                default_include = default_rss_setting.get("include")
                default_exclude = default_rss_setting.get("exclude")
                default_free = default_rss_setting.get("free")
                default_download_setting = default_rss_setting.get("download_setting")
                default_over_edition = default_rss_setting.get("over_edition")
                if filter_restype is None and default_restype:
                    filter_restype = default_restype
                if filter_pix is None and default_pix:
                    filter_pix = default_pix
                if filter_team is None and default_team:
                    filter_team = default_team
                if filter_rule is None and default_rule:
                    filter_rule = int(default_rule) if str(default_rule).isdigit() else None
                if filter_include is None and default_include:
                    filter_include = default_include
                if filter_exclude is None and default_exclude:
                    filter_exclude = default_exclude
                if filter_free is None and default_free is not None:
                    filter_free = bool(default_free)
                if over_edition is None and default_over_edition:
                    over_edition = 1 if default_over_edition == "1" else 0
                if download_setting is None and default_download_setting:
                    download_setting = (
                        int(default_download_setting)
                        if str(default_download_setting).replace("-", "").isdigit()
                        else None
                    )
                # 站点留空表示"全部当前用户可见站点"：不再强制继承默认设置，
                # 由搜索/RSS 执行时按用户可见站点兜底，避免"未配置即搜不到"

        rss_sites = rss_sites or []
        if isinstance(rss_sites, str):
            rss_sites = rss_sites.split(",")
        search_sites = search_sites or []
        if isinstance(search_sites, str):
            search_sites = search_sites.split(",")
        over_edition = 1 if over_edition else 0
        filter_rule = int(str(filter_rule)) if str(filter_rule).isdigit() else 0
        total_ep = int(str(total_ep)) if str(total_ep).isdigit() else None
        current_ep = int(str(current_ep)) if str(current_ep).isdigit() else None
        download_setting = int(str(download_setting)) if str(download_setting).replace("-", "").isdigit() else -1
        fuzzy_match = bool(fuzzy_match)

        provider_ref = _split_provider_ref(metadata_ref)
        source_provider = str(provider or (provider_ref[0] if provider_ref else "")).strip().lower() or None
        source_ref = str(metadata_ref).strip() if metadata_ref else None
        if not fuzzy_match:
            media_info = None
            if provider_ref:
                descriptor = getattr(metadata_registry.get_provider(provider_ref[0]), "descriptor", None)
                if name and getattr(descriptor, "visibility", "public") == "private":
                    # 私有插件来源已有标题时先落库，详情和海报由插件列表异步补全，
                    # 避免被外部详情源/Cloudflare 请求阻塞。
                    media_info = meta_info(title=name, mtype=mtype)
                    media_info.title = name
                    media_info.cn_name = name
                    media_info.year = year or media_info.year
                    media_info.type = mtype
                    media_info.content_profile = content_profile or "default"
                    if image:
                        media_info.poster_path = image
                    # 只有缺海报时才同步抓详情；已有海报直接落库，避免聚合详情阻塞订阅。
                    if not media_info.poster_path:
                        poster, real_source = _resolve_provider_poster(provider_ref[0], provider_ref[1], mtype)
                        if poster:
                            media_info.poster_path = poster
                        if real_source:
                            media_info.provider_data = {
                                **(getattr(media_info, "provider_data", None) or {}),
                                "source_provider": real_source,
                            }
                else:
                    media_info = self._provider_media_info(
                        provider_ref[0],
                        provider_ref[1],
                        name=name,
                        year=year,
                        content_profile=content_profile,
                        allow_private=allow_private,
                        permissions=permissions,
                        media_type=mtype,
                        season=int(str(season)) if str(season or "").isdigit() else None,
                    )
                if media_info is not None:
                    media_info.tmdb_id = provider_ref[1] if provider_ref[0] == "tmdb" else ""
                    mtype = media_info.type
                    # 插件详情源熔断/超时时，用内容画像聚合源补海报，避免订阅卡片空白。
                    if not media_info.poster_path and content_profile:
                        profile_ref = _split_provider_ref(mediaid)
                        if profile_ref:
                            poster, _ = _resolve_provider_poster(content_profile, profile_ref[1], mtype)
                            if poster:
                                media_info.poster_path = poster
                    # 元数据来源判定为动漫时同步切换内容画像，避免落库成默认电视剧。
                    if mtype == MediaType.ANIME and str(content_profile or "").strip() in ("", "default"):
                        content_profile = "anime"
                        media_info.content_profile = "anime"
                    anchor_ref = _split_provider_ref(mediaid)
                    if anchor_ref:
                        media_info.anchor_provider = anchor_ref[0]
                        media_info.anchor_external_id = anchor_ref[1]
                    if not keyword:
                        # 动漫按标题搜索；只有插件内容画像才用内容编号/锚点作为关键词。
                        profile_key = str(content_profile or "").strip()
                        prefer_anchor = profile_key not in ("", "default", "anime")
                        if prefer_anchor and anchor_ref:
                            # 插件内容画像的锚点可能误带完整标题；关键词只取内容编号段。
                            keyword = str(anchor_ref[1]).strip().split()[0]
                        else:
                            keyword = media_info.title or name or provider_ref[1]
                    if keyword and str(keyword).startswith("content_id:"):
                        keyword = str(keyword).split(":", 1)[1]
                    media_info.keyword = keyword
                    media_info.provider = source_provider
                    media_info.metadata_ref = source_ref
            if media_info is None and mediaid:
                media_info = self._web_utils.get_mediainfo_from_id(mtype=mtype, mediaid=mediaid)
                if not season and media_info:
                    season = media_info.begin_season
            elif media_info is None:
                if season:
                    title = "%s %s 第%s季".strip() % (name, year, season)
                else:
                    title = "%s %s".strip() % (name, year)
                media_info = self._media.get_media_info(title=title, mtype=mtype, strict=bool(year), cache=False)
            if media_info is None:
                return 1, "无法查询到媒体信息", None
            if image:
                media_info.poster_path = image
            has_source = bool(
                media_info.provider_data
                or getattr(media_info, "douban_id", None)
                or str(mediaid or "").startswith(("DB:", "BG:"))
                or getattr(media_info, "anchor_provider", None)
                or provider_ref is not None
            )
            if not has_source:
                return 1, "无法查询到媒体信息", None
            if media_info.type != MediaType.MOVIE:
                if not season:
                    if media_info.provider_data:
                        total_seasoninfo = self._media.get_tmdb_tv_seasons(tv_info=media_info.provider_data)
                        if not total_seasoninfo:
                            return 2, "获取剧集信息失败", media_info
                        total_seasoninfo = sorted(total_seasoninfo, key=lambda x: x.get("season_number"), reverse=True)
                        season = total_seasoninfo[0].get("season_number")
                        total_episode = total_seasoninfo[0].get("episode_count")
                    else:
                        season = media_info.begin_season or 1
                        total_episode = media_info.total_episodes or 0
                else:
                    total_episode = total_ep or (
                        self._media.get_tmdb_season_episodes_num(
                            tv_info=media_info.provider_data, season=_season_number(season)
                        )
                        if media_info.provider_data
                        else (media_info.total_episodes or 0)
                    )
                if not total_episode and media_info.provider_data:
                    return 3, f"第{season}季获取剧集数失败，请确认该季是否存在", media_info
                media_info.begin_season = _season_number(season, 0)
                media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                # 重订阅续订：始终从转移记录/下载历史推导断点（历史推导只向前，不倒退），
                # 避免重新订阅从头重复下载已下载剧集，或前端传入旧 current_ep 导致进度卡住。
                # current_ep 语义 = 首个待下载集（与 RSS 兜底 range(current_ep, total+1) 一致）；
                # 已获得连续 N 集 → 首个待下载 = N+1。转移记录集数最可靠，二者取较大值。
                if media_info.tmdb_id and not str(media_info.tmdb_id).startswith("DB:"):
                    continue_ep = 0
                    # start = 订阅起点（首个待下载集）：中途订阅从第 N 集开始跟踪时，
                    # 历史只有 N 之后的集，须从 N 数起而非从第 1 集（否则误判为 0）
                    sub_start = int(current_ep) if current_ep and str(current_ep).isdigit() else 1
                    if self._transfer_history_manager:
                        try:
                            continue_ep = self._transfer_history_manager.get_contiguous_transferred_episode_by_tmdb(
                                media_info.tmdb_id, _season_number(season, 1), start=sub_start
                            )
                        except Exception as e:  # noqa: BLE001
                            log.debug(f"[SubscribeAdd] 查询转移历史失败: {e}")
                    if self._download_repo:
                        try:
                            continue_ep = max(
                                continue_ep,
                                self._download_repo.get_contiguous_completed_episode_by_tmdb(
                                    media_info.tmdb_id, _season_number(season, 1), start=sub_start
                                ),
                            )
                        except Exception as e:  # noqa: BLE001
                            log.debug(f"[SubscribeAdd] 查询下载历史失败: {e}")
                    if continue_ep > 0:
                        # 历史推导只向前：取 历史推导点 与 已传入/显式 current_ep 的较大者，
                        # 避免前端回传旧进度把已转移的集误标回缺失
                        current_ep = max(current_ep or 0, continue_ep + 1)
                        log.info(
                            f"[SubscribeAdd]{media_info.get_title_string()} S{season} "
                            f"历史记录已有 {continue_ep} 集，从第 {current_ep} 集开始续订"
                        )
                else:
                    # 非 TMDB 订阅按统一身份恢复断点，避免重订阅后从第 1 集重复下载。
                    ref = media_info.get_media_ref()
                    if ref is not None:
                        continue_ep = 0
                        sub_start = int(current_ep) if current_ep and str(current_ep).isdigit() else 1
                        ref_key = f"{ref.provider}:{ref.external_id}"
                        if self._transfer_history_manager:
                            try:
                                continue_ep = self._transfer_history_manager.get_contiguous_transferred_episode_by_ref(
                                    ref_key,
                                    _season_number(season, 1),
                                    media_type=str(media_info.type.value) if media_info.type else None,
                                    start=sub_start,
                                )
                            except Exception as e:  # noqa: BLE001
                                log.debug(f"[SubscribeAdd] 查询转移历史失败: {e}")
                        if self._download_repo:
                            try:
                                continue_ep = max(
                                    continue_ep,
                                    self._download_repo.get_contiguous_completed_episode_by_ref(
                                        identity_id=getattr(media_info, "identity_id", None),
                                        anchor_provider=ref.provider,
                                        anchor_external_id=ref.external_id,
                                        season=_season_number(season, 1),
                                        start=sub_start,
                                    ),
                                )
                            except Exception as e:  # noqa: BLE001
                                log.debug(f"[SubscribeAdd] 查询下载历史失败: {e}")
                        if continue_ep > 0:
                            current_ep = max(current_ep or 0, continue_ep + 1)
                            log.info(
                                f"[SubscribeAdd]{media_info.get_title_string()} S{season} "
                                f"身份历史已有 {continue_ep} 集，从第 {current_ep} 集开始续订"
                            )
                if current_ep:
                    # 首个待下载集为 current_ep → 缺失集数 = total - current_ep + 1
                    lack = max(0, total - current_ep + 1)
                else:
                    lack = total
                identity_fields = self._identity_fields(
                    media_info,
                    mtype,
                    mediaid,
                    metadata_policy,
                    content_profile,
                    naming_profile,
                )
                rssid = self._tv_repo.insert(
                    media_info=media_info,
                    total=total,
                    lack=lack,
                    **identity_fields,
                    state=state,
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
                    fuzzy_match=0,
                    desc=media_info.overview,
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                    user_id=user_id,
                    provider=source_provider,
                    metadata_ref=source_ref,
                )
                code = 0 if rssid not in (-1, 9) else rssid
            else:
                identity_fields = self._identity_fields(
                    media_info,
                    mtype,
                    mediaid,
                    metadata_policy,
                    content_profile,
                    naming_profile,
                )
                rssid = self._movie_repo.insert(
                    media_info=media_info,
                    state=state,
                    **identity_fields,
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_free=filter_free,
                    filter_exclude=filter_exclude,
                    save_path=save_path,
                    download_setting=download_setting,
                    fuzzy_match=0,
                    desc=media_info.overview,
                    note=gen_rss_note(media_info),
                    keyword=keyword,
                    user_id=user_id,
                    provider=source_provider,
                    metadata_ref=source_ref,
                )
                code = 0 if rssid not in (-1, 9) else rssid
        else:
            media_info = meta_info(title=name, mtype=mtype)
            media_info.title = name
            media_info.type = mtype
            if mtype == MediaType.ANIME and str(content_profile or "").strip() in ("", "default"):
                content_profile = "anime"
            media_info.content_profile = content_profile or "default"
            media_info.keyword = keyword
            media_info.content_profile = content_profile or "default"
            media_info.provider = source_provider
            media_info.metadata_ref = source_ref
            if image:
                media_info.poster_path = image
            if year:
                media_info.year = str(year)
            if season:
                media_info.begin_season = _season_number(season)
            if mtype == MediaType.MOVIE:
                identity_fields = self._identity_fields(
                    media_info,
                    mtype,
                    mediaid,
                    metadata_policy,
                    content_profile,
                    naming_profile,
                )
                rssid = self._movie_repo.insert(
                    media_info=media_info,
                    state=SubscribeState.RUNNING.value,
                    **identity_fields,
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_rule=filter_rule,
                    filter_free=filter_free,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    save_path=save_path,
                    download_setting=download_setting,
                    fuzzy_match=1,
                    keyword=keyword,
                    user_id=user_id,
                    provider=source_provider,
                    metadata_ref=source_ref,
                )
                code = 0 if rssid not in (-1, 9) else rssid
            else:
                identity_fields = self._identity_fields(
                    media_info,
                    mtype,
                    mediaid,
                    metadata_policy,
                    content_profile,
                    naming_profile,
                )
                rssid = self._tv_repo.insert(
                    media_info=media_info,
                    total=0,
                    lack=0,
                    **identity_fields,
                    state=SubscribeState.RUNNING.value,
                    rss_sites=rss_sites,
                    search_sites=search_sites,
                    over_edition=over_edition,
                    filter_restype=filter_restype,
                    filter_pix=filter_pix,
                    filter_team=filter_team,
                    filter_free=filter_free,
                    filter_rule=filter_rule,
                    filter_include=filter_include,
                    filter_exclude=filter_exclude,
                    save_path=save_path,
                    download_setting=download_setting,
                    fuzzy_match=1,
                    keyword=keyword,
                    user_id=user_id,
                    provider=source_provider,
                    metadata_ref=source_ref,
                )
                code = 0 if rssid not in (-1, 9) else rssid

        if code == 0:
            # 归属信息必须先写入再发布事件/发通知，否则事件订阅方和定向通知会丢失 owner。
            media_info.user_name = user_name
            media_info.user_id = user_id
            self._event_bus.publish(
                Event(
                    event_type=SUBSCRIBE_ADD,
                    payload=asdict(
                        SubscribeAddPayload(
                            media=media_info.to_dict(),
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
            self._message.send_subscribe_success_message(
                in_from=cast(SubscribeType, in_from or SubscribeType.Manual),
                media_info=media_info,
            )
            return code, "添加订阅成功", media_info
        elif code == 9:
            return code, "订阅已存在", media_info
        else:
            return code, "添加订阅失败", media_info
