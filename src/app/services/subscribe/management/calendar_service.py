"""Subscribe calendar service — 订阅日历事件聚合."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import log
from app.db.repositories.subscribe_calendar_repo_adapter import SubscribeCalendarRepositoryAdapter
from app.domain.media_types import ProviderMediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.schemas.auth import UserContext

if TYPE_CHECKING:
    from app.services.media_info_service import MediaInfoService
    from app.services.rss_automation.task_service import RssTaskService
    from app.services.subscribe.management.service import SubscribeService


def _escape_ics_text(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n").replace("\r", "")
    )


def _format_ics_date(date_str: str) -> str:
    return date_str.replace("-", "")


def _normalized_title(title: str) -> str:
    return "".join(ch for ch in str(title or "").lower() if ch.isalnum())


def _provider_label(provider: str, metadata_gateway: MetadataGateway | None = None) -> str:
    if metadata_gateway is None:
        return str(provider or "").strip()
    return metadata_gateway.provider_display_name(provider).strip()


class SubscribeCalendarService:
    """订阅日历服务 — 聚合电影/电视剧的日历事件."""

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        media_info_service: MediaInfoService,
        subscribe: SubscribeService,
        rss_task_service: RssTaskService,
        metadata_gateway: MetadataGateway | None = None,
        calendar_event_repo: SubscribeCalendarRepositoryAdapter | None = None,
    ):
        self._media_info_service = media_info_service
        self._subscribe = subscribe
        self._rss_task_service = rss_task_service
        self._metadata_gateway = metadata_gateway
        self._calendar_event_repo = calendar_event_repo or SubscribeCalendarRepositoryAdapter()
        self._refreshing_users: set[int] = set()
        self._refresh_executor = ThreadPoolExecutor(max_workers=1)
        self._episode_cache: dict[tuple[str, str, int], tuple[float, list[dict]]] = {}
        self._episode_cache_ttl = 600.0
        self._movie_cache: dict[str, tuple[float, dict | None]] = {}
        self._movie_cache_ttl = 600.0
        self._events_cache: dict[str, tuple[float, float, list[dict]]] = {}
        self._last_good_events: dict[str, list[dict]] = {}
        self._persistent_events = get_cache_manager().get_or_create(
            "subscribe_calendar_events", cache_type="redis", ttl=86_400
        )
        self._events_cache_ttl = 600.0

    def _context(self, user: UserContext | None, *, content_profile: str, purpose: str) -> MetadataContext:
        permissions = frozenset(getattr(user, "permissions", ()) or ())
        allow_private = bool(user and user.has_permission("metadata:private:view"))
        return MetadataContext(
            user_id=getattr(user, "user_id", None),
            permissions=permissions,
            content_profile=content_profile or "default",
            purpose=purpose,
            allow_private=allow_private,
        )

    def _lookup(self, provider: str, external_id: str, user: UserContext | None, **kwargs):
        if self._metadata_gateway is None:
            return None
        kwargs.pop("allow_private", None)
        kwargs.pop("permissions", None)
        kwargs["context"] = self._context(
            user,
            content_profile=str(kwargs.get("content_profile") or "default"),
            purpose="subscribe.calendar",
        )
        return self._metadata_gateway.lookup(provider, external_id, **kwargs)

    def get_movie_items(self, user: UserContext | None = None) -> list[dict]:
        """获取电影订阅项目（含非 TMDB 的插件内容画像）."""
        items = []
        for movie in self._subscribe.get_subscribe_movies(user=user).values():
            tmdbid = movie.get("tmdbid")
            provider = str(movie.get("anchor_provider") or "").strip()
            external_id = str(movie.get("anchor_external_id") or "").strip()
            if not tmdbid and not (provider and external_id):
                continue
            items.append(
                {
                    "id": tmdbid,
                    "rssid": movie.get("id"),
                    "name": movie.get("name"),
                    "year": movie.get("year"),
                    "image": movie.get("image"),
                    "release_date": movie.get("release_date"),
                    "provider": provider,
                    "external_id": external_id,
                    "metadata_ref": movie.get("metadata_ref"),
                    "source_label": movie.get("source_label"),
                    "content_profile": movie.get("content_profile"),
                }
            )
        return items

    def get_tv_items(self, user: UserContext | None = None) -> list[dict]:
        """获取电视剧订阅项目列表（含去重；user 非空时按数据归属过滤）."""
        rss_tv_items = []
        for tv in self._subscribe.get_subscribe_tvs(user=user).values():
            if not tv.get("season"):
                continue
            season = int(str(tv.get("season")).replace("S", "") or 1)
            tmdbid = tv.get("tmdbid")
            provider = str(tv.get("anchor_provider") or "").strip()
            external_id = str(tv.get("anchor_external_id") or "").strip()
            if not tmdbid and not (provider and external_id):
                continue
            rss_tv_items.append(
                {
                    "id": tmdbid,
                    "rssid": tv.get("id"),
                    "season": season,
                    "name": tv.get("name"),
                    "provider": provider,
                    "external_id": external_id,
                    "image": tv.get("image"),
                    "year": tv.get("year"),
                    "content_profile": tv.get("content_profile"),
                }
            )
        rss_tv_items += self._rss_task_service.get_userrss_mediainfos(user=user)
        uniques = set()
        unique_tv_items = []
        for item in rss_tv_items:
            unique = f"{item.get('provider')}:{item.get('external_id') or item.get('id')}_{item.get('season')}"
            if unique not in uniques:
                uniques.add(unique)
                unique_tv_items.append(item)
        return unique_tv_items

    def generate_ics(self, user: UserContext | None = None) -> str:
        """生成 iCalendar (.ics) 格式文本."""
        events = self.get_events(user=user)
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nexus Media//Subscription Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        for event in events:
            uid = f"{event.get('id')}-{event.get('rssid', '0')}@nexus-media"
            start = _format_ics_date(str(event.get("start") or ""))
            if not start:
                continue
            end = (datetime.strptime(start, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
            event_type = event.get("type")
            type_label = "电影" if event_type == "movie" else "动漫" if event_type == "anime" else "电视剧"
            summary = _escape_ics_text(event.get("title"))
            year = event.get("year")
            year_part = f" ({year})" if year else ""
            source_label = str(event.get("source_label") or "").strip()
            date_source = str(event.get("date_source_label") or "").strip()
            source_part = f" · 订阅源:{source_label}" if source_label else ""
            if date_source and date_source != source_label:
                source_part += f" · 日期源:{date_source}"
            description = _escape_ics_text(f"{type_label} - {event.get('title')}{year_part}{source_part}")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTART;VALUE=DATE:{start}",
                    f"DTEND;VALUE=DATE:{end}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                    "TRANSP:TRANSPARENT",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    def _provider_episodes(
        self,
        provider: str,
        external_id: str,
        season: int,
        user: UserContext | None,
    ) -> list[dict]:
        if self._metadata_gateway is None:
            return []
        key = (provider, external_id, season)
        cached = self._episode_cache.get(key)
        if cached and time.monotonic() - cached[0] < self._episode_cache_ttl:
            return cached[1]
        try:
            episodes = self._metadata_gateway.episodes(
                provider,
                external_id,
                season,
                context=self._context(user, content_profile="default", purpose="subscribe.calendar"),
            )
        except Exception:  # noqa: BLE001 - 单个来源失败不影响其余日历事件
            episodes = []
        self._episode_cache[key] = (time.monotonic(), episodes)
        return episodes

    def get_events(self, user: UserContext | None = None) -> list[dict]:
        """读取数据库日历事件；首次为空或超过 1 小时才后台刷新."""
        if user is None:
            return self._fetch_events(user)
        user_id = int(user.user_id) if user.user_id else 0
        stored = self._calendar_event_repo.get_user_events(user_id)
        if stored:
            updated_at = self._calendar_event_repo.get_user_updated_at(user_id)
            if updated_at and (datetime.now() - updated_at).total_seconds() > 3600:
                self._schedule_refresh(user_id, user)
            return stored
        return self.refresh_events(user)

    def refresh_events(self, user: UserContext | None = None) -> list[dict]:
        """从元数据源刷新并写入数据库；空结果不覆盖已有事件."""
        events = self._fetch_events(user)
        if events and user is not None and user.user_id:
            self._calendar_event_repo.replace_user_events(int(user.user_id), events)
        return events

    def _schedule_refresh(self, user_id: int, user: UserContext | None) -> None:
        if user_id in self._refreshing_users:
            return
        self._refreshing_users.add(user_id)

        def _run() -> None:
            try:
                self.refresh_events(user)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[Calendar]后台刷新失败 user={user_id}: {exc}")
            finally:
                self._refreshing_users.discard(user_id)

        self._refresh_executor.submit(_run)

    def _fetch_events(self, user: UserContext | None = None) -> list[dict]:
        """从元数据源实时聚合（由刷新任务/首次读取调用）."""
        user_id = int(user.user_id) if user and user.user_id else 0
        cache_key = f"user:{user_id}"
        persistent = self._persistent_events if user_id else None
        movie_items = self.get_movie_items(user=user)
        tv_items = self.get_tv_items(user=user)
        poster_by_rssid = {
            str(item.get("rssid")): str(item.get("image") or "")
            for item in [*movie_items, *tv_items]
            if item.get("rssid") is not None and item.get("image")
        }

        def fill_posters(items: list[dict]) -> list[dict]:
            for event in items:
                if not event.get("poster"):
                    event["poster"] = poster_by_rssid.get(str(event.get("rssid")), "")
            return items

        cached = self._events_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < cached[1]:
            return [dict(event) for event in fill_posters([dict(e) for e in cached[2]])]
        events: list[dict] = []
        total = len(movie_items) + len(tv_items)
        complete = True
        if total:
            executor = ThreadPoolExecutor(max_workers=min(12, total))
            futures = [executor.submit(self._movie_events, movie, user) for movie in movie_items]
            futures.extend(executor.submit(self._tv_events, tv, user) for tv in tv_items)
            done, pending = wait(futures, timeout=30.0)
            # 关键：不能 wait=True 退出，否则慢 provider 会继续阻塞 HTTP 响应。
            executor.shutdown(wait=False, cancel_futures=False)
            complete = not pending
            for future in done:
                try:
                    events.extend(future.result() or [])
                except Exception:  # noqa: BLE001 - 单个订阅失败不影响日历
                    continue
        events = [event for event in events if event.get("start")]
        fallback = self._last_good_events.get(cache_key)
        if not fallback and persistent is not None:
            persisted = persistent.get(cache_key)
            fallback = persisted if isinstance(persisted, list) else None

        if complete and (events or not fallback):
            if fallback and events and len(events) < len(fallback):
                # 聚合结果比上次完整结果少时合并，避免限流导致旧事件消失。
                merged = {
                    str(event.get("id") or f"{event.get('start')}:{event.get('title')}"): event for event in fallback
                }
                for event in events:
                    merged[str(event.get("id") or f"{event.get('start')}:{event.get('title')}")] = event
                events = list(merged.values())
            if events:
                self._last_good_events[cache_key] = [dict(event) for event in events]
                if persistent is not None:
                    persistent.set(cache_key, events)
        elif fallback:
            # provider 限流/超时只影响部分订阅时，用最近一次完整结果补齐，避免事件凭空消失。
            merged = {str(event.get("id") or f"{event.get('start')}:{event.get('title')}"): event for event in fallback}
            for event in events:
                merged[str(event.get("id") or f"{event.get('start')}:{event.get('title')}")] = event
            events = list(merged.values())
        fill_posters(events)
        events.sort(key=lambda event: str(event.get("start") or ""))
        # 插件电影首次可能因插件尚未就绪而无日期；此时短缓存，避免错误结果锁 10 分钟。
        plugin_rssids = {item.get("rssid") for item in movie_items if not item.get("id")}
        has_plugin_event = any(event.get("rssid") in plugin_rssids for event in events)
        # 不完整结果只短暂缓存，下一轮尽快重新聚合，避免慢订阅被缓存成“缺失”。
        ttl = self._events_cache_ttl if complete and (not plugin_rssids or has_plugin_event) else 5.0
        self._events_cache[cache_key] = (time.monotonic(), ttl, events)
        return [dict(event) for event in events]

    def _movie_events(self, movie: dict, user: UserContext | None = None) -> list[dict]:
        if movie.get("id"):
            info = self._media_info_service.get_movie_calendar(tid=movie.get("id"), rssid=movie.get("rssid"))
            if info and info.get("id"):
                info["source_label"] = "TMDB"
                info["date_source_label"] = "TMDB"
                info["content_profile"] = str(movie.get("content_profile") or "default")
                return [info]
            return []
        event = self._plugin_movie_event(movie, user)
        return [event] if event else []

    def _tv_events(self, tv: dict, user: UserContext | None = None) -> list[dict]:
        profile = str(tv.get("content_profile") or "default")
        if tv.get("id"):
            infos = self._media_info_service.get_tv_calendar(
                tid=tv.get("id"),
                season=tv.get("season"),
                name=tv.get("name"),
                rssid=tv.get("rssid"),
            )
            events = []
            if infos and isinstance(infos, list):
                anime = profile == "anime"
                for info in infos:
                    if info.get("id"):
                        if anime:
                            info["type"] = "anime"
                        info["source_label"] = "TMDB"
                        info["date_source_label"] = "TMDB"
                        info["content_profile"] = profile
                        events.append(info)
            return events

        provider = str(tv.get("provider") or "").strip()
        external_id = str(tv.get("external_id") or "").strip()
        if not provider or not external_id:
            return []
        # 豆瓣 HTML 分集页有 PoW + 每集抓取，日历热路径直接走 TMDB 兜底。
        if provider == "douban":
            provider_events = []
        else:
            provider_events = self._provider_tv_events(tv, provider, external_id, user)
        if provider_events:
            return provider_events
        fallback_events = self._tmdb_fallback_events(tv, user)
        source_label = _provider_label(provider, self._metadata_gateway) or provider.upper()
        for event in fallback_events:
            event["source_label"] = source_label
            event["date_source_label"] = "TMDB"
        return fallback_events

    def _provider_tv_events(self, tv: dict, provider: str, external_id: str, user: UserContext | None) -> list[dict]:
        name = str(tv.get("name") or "")
        profile = str(tv.get("content_profile") or "default")
        events = []
        for episode in self._provider_episodes(provider, external_id, int(tv.get("season") or 1), user):
            air_date = str(episode.get("air_date") or "").strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", air_date):
                continue
            number = episode.get("episode_number")
            ep_title = str(episode.get("title") or "").strip()
            title = name
            if number is not None:
                title = f"{title} 第{number}集"
            if ep_title:
                title = f"{title} {ep_title}"
            source_label = _provider_label(provider, self._metadata_gateway) or provider.upper()
            events.append(
                {
                    "id": f"{provider}:{external_id}:{tv.get('season')}:{number}",
                    "title": title.strip(),
                    "start": air_date,
                    "type": "anime" if profile == "anime" else "tv",
                    "poster": tv.get("image") or "",
                    "vote_average": "",
                    "year": tv.get("year") or "",
                    "rssid": tv.get("rssid"),
                    "season": tv.get("season"),
                    "episode": number,
                    "source_label": source_label,
                    "date_source_label": source_label,
                    "content_profile": profile,
                }
            )
        return events

    def _detail_provider_key(self, profile: str, user: UserContext | None = None) -> str:
        """按内容画像选择能提供详情的能力源（优先键名与画像一致）。"""
        if self._metadata_gateway is None or not profile or profile == "default":
            return ""
        allow_private = bool(user and user.has_permission("metadata:private:view"))
        permissions = set(user.permissions) if user else None
        try:
            providers = self._metadata_gateway.list_providers(
                context=self._context(user, content_profile=profile, purpose="subscribe.calendar"),
                allow_private=allow_private,
                permissions=permissions,
                probe_health=False,
            )
        except Exception:  # noqa: BLE001 - 能力源列表失败则跳过
            return ""
        candidates = [
            item
            for item in providers
            if profile in (item.get("content_profiles") or [])
            and any("detail" in str(cap).lower() for cap in item.get("capabilities", []))
        ]
        if not candidates:
            return ""
        return str(
            candidates[0]["provider"] if not any(item["provider"] == profile for item in candidates) else profile
        )

    def _plugin_movie_event(self, movie: dict, user: UserContext | None = None) -> dict | None:
        if self._metadata_gateway is None:
            return None
        key = str(movie.get("external_id") or movie.get("metadata_ref") or "")
        if not key:
            return None
        cached = self._movie_cache.get(key)
        if cached and time.monotonic() - cached[0] < self._movie_cache_ttl:
            return cached[1]

        ref_provider = ""
        ref_external = ""
        metadata_ref = str(movie.get("metadata_ref") or "").strip()
        if ":" in metadata_ref:
            ref_provider, ref_external = metadata_ref.split(":", 1)
            if ref_provider in ("content_id", ""):
                ref_provider = ref_external = ""
        provider = ref_provider or str(movie.get("provider") or "")
        external_id = ref_external or str(movie.get("external_id") or "")
        profile = str(movie.get("content_profile") or "default")
        allow_private = bool(user and user.has_permission("metadata:private:view"))
        permissions = set(user.permissions) if user else None

        record = None
        used_provider = provider
        if provider and external_id:
            try:
                record = self._lookup(
                    provider,
                    external_id,
                    user,
                    media_type=ProviderMediaType.MOVIE,
                    scope="default",
                    allow_private=allow_private,
                    content_profile=profile,
                    permissions=permissions,
                )
            except Exception:  # noqa: BLE001 - 单来源失败后尝试聚合
                record = None
        detail_provider = ""
        if not record and profile not in ("", "default") and movie.get("external_id"):
            # 插件画像以内容锚点走能力源聚合，避免单一 provider 详情失败。
            detail_provider = self._detail_provider_key(profile, user)
            if detail_provider:
                try:
                    record = self._lookup(
                        detail_provider,
                        str(movie.get("external_id")),
                        user,
                        media_type=ProviderMediaType.MOVIE,
                        scope="release",
                        allow_private=allow_private,
                        content_profile=profile,
                        permissions=permissions,
                    )
                    used_provider = detail_provider
                except Exception:  # noqa: BLE001 - 聚合失败则跳过该电影
                    record = None
        release_date = str((record or {}).get("release_date") or movie.get("release_date") or "").strip()
        event = None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
            poster = ""
            images = (record or {}).get("images") or {}
            poster_list = images.get("poster") or []
            if poster_list:
                poster = str(poster_list[0].get("url") or "")
            source_label = str(movie.get("source_label") or "").strip() or _provider_label(
                provider, self._metadata_gateway
            )
            date_source = (
                "插件聚合"
                if detail_provider and used_provider == detail_provider
                else (_provider_label(used_provider, self._metadata_gateway) or used_provider)
            )
            event = {
                "id": f"{provider or used_provider}:{external_id}",
                "title": movie.get("name") or (record or {}).get("title") or "",
                "start": release_date,
                "type": "movie",
                "poster": poster or movie.get("image") or "",
                "vote_average": "",
                "year": release_date[:4],
                "rssid": movie.get("rssid"),
                "source_label": source_label,
                "date_source_label": date_source,
                "content_profile": profile,
            }
        if event is not None:
            self._movie_cache[key] = (time.monotonic(), event)
        else:
            self._movie_cache.pop(key, None)
        return event

    def _tmdb_fallback_events(self, tv: dict, user: UserContext | None = None) -> list[dict]:
        if self._metadata_gateway is None:
            return []
        name = str(tv.get("name") or "").strip()
        if not name:
            return []
        profile = str(tv.get("content_profile") or "default")
        media_type = ProviderMediaType.ANIME if profile == "anime" else ProviderMediaType.SERIES
        try:
            hits = self._metadata_gateway.search(
                query=name,
                context=self._context(user, content_profile=profile, purpose="subscribe.calendar"),
                provider="tmdb",
                media_type=media_type,
                content_profile=profile,
                limit=5,
            )
        except Exception:  # noqa: BLE001 - TMDB 兜底失败不影响其他来源
            return []
        target = _normalized_title(name)
        year = str(tv.get("year") or "")
        hit = next(
            (
                item
                for item in hits
                if _normalized_title(item.get("title") or "") == target
                or (year and str(item.get("year") or "") == year)
            ),
            hits[0] if hits else None,
        )
        if not hit:
            return []
        infos = self._media_info_service.get_tv_calendar(
            tid=str(hit.get("ref", {}).get("external_id") or ""),
            season=int(tv.get("season") or 1),
            name=name,
            rssid=tv.get("rssid"),
        )
        if not infos or not isinstance(infos, list):
            return []
        for info in infos:
            if not info.get("id"):
                continue
            if media_type == ProviderMediaType.ANIME:
                info["type"] = "anime"
            info["source_label"] = "TMDB"
            info["content_profile"] = str(tv.get("content_profile") or "default")
        return [info for info in infos if info.get("id")]
