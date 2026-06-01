"""Subscribe calendar service — 订阅日历事件聚合."""

from app.di import container


class SubscribeCalendarService:
    """订阅日历服务 — 聚合电影/电视剧的日历事件."""

    def __init__(self, media_info_service=None, subscribe=None, rss_task_service=None):
        self._media_info_service = media_info_service or container.media_info_service()
        self._subscribe = subscribe or container.subscribe_service()
        self._rss_task_service = rss_task_service or container.rss_task_service()

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
