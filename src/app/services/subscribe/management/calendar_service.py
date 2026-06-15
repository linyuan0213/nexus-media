"""Subscribe calendar service — 订阅日历事件聚合."""

from datetime import datetime, timedelta

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


class SubscribeCalendarService:
    """订阅日历服务 — 聚合电影/电视剧的日历事件."""

    def __init__(
        self,
        media_info_service: MediaInfoService,
        subscribe: SubscribeService,
        rss_task_service: RssTaskService,
    ):
        self._media_info_service = media_info_service
        self._subscribe = subscribe
        self._rss_task_service = rss_task_service

    def get_movie_items(self) -> list[dict]:
        """获取电影订阅项目列表."""
        return [
            {"id": movie.get("tmdbid"), "rssid": movie.get("id")}
            for movie in self._subscribe.get_subscribe_movies().values()
            if movie.get("tmdbid")
        ]

    def get_tv_items(self) -> list[dict]:
        """获取电视剧订阅项目列表（含去重）."""
        rss_tv_items = [
            {
                "id": tv.get("tmdbid"),
                "rssid": tv.get("id"),
                "season": int(str(tv.get("season")).replace("S", "")),
                "name": tv.get("name"),
            }
            for tv in self._subscribe.get_subscribe_tvs().values()
            if tv.get("season") and tv.get("tmdbid")
        ]
        rss_tv_items += self._rss_task_service.get_userrss_mediainfos()
        uniques = set()
        unique_tv_items = []
        for item in rss_tv_items:
            unique = f"{item.get('id')}_{item.get('season')}"
            if unique not in uniques:
                uniques.add(unique)
                unique_tv_items.append(item)
        return unique_tv_items

    def generate_ics(self) -> str:
        """生成 iCalendar (.ics) 格式文本."""
        events = self.get_events()
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
            type_label = "电影" if event.get("type") == "movie" else "电视剧"
            summary = _escape_ics_text(event.get("title"))
            year = event.get("year")
            year_part = f" ({year})" if year else ""
            description = _escape_ics_text(f"{type_label} - {event.get('title')}{year_part}")
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

    def get_events(self) -> list[dict]:
        """获取订阅日历事件."""
        events = []
        for movie in self.get_movie_items():
            info = self._media_info_service.get_movie_calendar(tid=movie.get("id"), rssid=movie.get("rssid"))
            if info and info.get("id"):
                events.append(info)
        for tv in self.get_tv_items():
            infos = self._media_info_service.get_tv_calendar(
                tid=tv.get("id"), season=tv.get("season"), name=tv.get("name"), rssid=tv.get("rssid")
            )
            if infos and isinstance(infos, list):
                for info in infos:
                    if info.get("id"):
                        events.append(info)
        return events
