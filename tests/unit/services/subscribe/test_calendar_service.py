"""订阅日历：非 TMDB 来源分集播出日期."""

from typing import Any, cast

from app.services.subscribe.management.calendar_service import SubscribeCalendarService


class _FakeSubscribe:
    def get_subscribe_movies(self, user=None):
        return {}

    def get_subscribe_tvs(self, user=None):
        return {
            "1": {
                "id": 1,
                "tmdbid": "",
                "season": "S01",
                "name": "乱世千金",
                "anchor_provider": "bangumi",
                "anchor_external_id": "624085",
                "image": "poster.jpg",
                "year": "2026",
                "content_profile": "anime",
            }
        }


class _FakeRssTasks:
    def get_userrss_mediainfos(self, user=None):
        return []


class _FakeMediaInfo:
    def get_movie_calendar(self, **kwargs):
        return None

    def get_tv_calendar(self, **kwargs):
        return []


class _FakeMetadata:
    def __init__(self):
        self.calls = []

    def provider_display_name(self, provider):
        return str(provider or "")

    def episodes(self, provider, external_id, season, **kwargs):
        self.calls.append((provider, external_id, season, kwargs))
        return [
            {
                "episode_number": 1,
                "title": "第一话",
                "air_date": "2026-07-01",
            },
            {
                "episode_number": 2,
                "title": "第二话",
                "air_date": "2026-07-08",
            },
            {
                "episode_number": 3,
                "title": "未播出",
                "air_date": None,
            },
        ]


def _service(metadata=None):
    return SubscribeCalendarService(
        media_info_service=cast(Any, _FakeMediaInfo()),
        subscribe=cast(Any, _FakeSubscribe()),
        rss_task_service=cast(Any, _FakeRssTasks()),
        metadata_gateway=cast(Any, metadata or _FakeMetadata()),
    )


class TestNonTmdbCalendar:
    def test_events_use_provider_air_dates(self):
        metadata = _FakeMetadata()
        events = _service(metadata).get_events()
        assert [event["start"] for event in events] == ["2026-07-01", "2026-07-08"]
        assert events[0]["title"] == "乱世千金 第1集 第一话"
        assert events[0]["type"] == "anime"
        assert events[0]["rssid"] == 1
        assert metadata.calls[0][:3] == ("bangumi", "624085", 1)

    def test_ics_contains_non_tmdb_episode(self):
        ics = _service().generate_ics()
        assert "DTSTART;VALUE=DATE:20260701" in ics
        assert "乱世千金" in ics
