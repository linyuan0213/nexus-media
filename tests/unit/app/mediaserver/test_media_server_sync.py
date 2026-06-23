"""MediaServer 同步逻辑单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.mediaserver.client.fnos import FnOS
from app.mediaserver.media_server import MediaServer


class TestMediaTypeFromString:
    """MediaType.from_string 应能识别各媒体服务器返回的类型别名."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Movie", MediaType.MOVIE),
            ("movie", MediaType.MOVIE),
            ("TV", MediaType.TV),
            ("tv", MediaType.TV),
            ("Series", MediaType.TV),
            ("show", MediaType.TV),
            ("anime", MediaType.ANIME),
            ("unknown", MediaType.UNKNOWN),
            ("", MediaType.UNKNOWN),
        ],
    )
    def test_from_string_recognizes_server_type_aliases(self, raw, expected):
        assert MediaType.from_string(raw) == expected


class TestFnOSGetItems:
    """FnOS.get_items 应能正确按媒体库过滤."""

    @patch.object(FnOS, "_refresh")
    def test_get_items_fallback_when_parent_filter_returns_empty(self, mock_refresh):
        client = FnOS.__new__(FnOS)
        client._fnos = MagicMock()
        client._play_host = "http://127.0.0.1:8003/"

        # API 按库过滤返回空，但全量返回包含目标库的数据
        client._fnos.fetch_all_pages.side_effect = [
            [],
            [
                {
                    "guid": "movie-1",
                    "ancestor_guid": "lib-movie",
                    "type": "Movie",
                    "title": "Movie A",
                    "air_date": "2023-01-01",
                    "imdb_id": "tt123",
                },
                {
                    "guid": "tv-1",
                    "ancestor_guid": "lib-tv",
                    "type": "TV",
                    "title": "TV A",
                    "air_date": "2022-06-01",
                    "imdb_id": "tt456",
                },
            ],
        ]

        items = list(client.get_items("lib-movie"))
        # 过滤掉末尾的 yield {}
        items = [item for item in items if item]

        assert len(items) == 1
        assert items[0]["id"] == "movie-1"
        assert items[0]["type"] == MediaType.MOVIE.value
        assert items[0]["library"] == "lib-movie"

        # 确认回退到全量获取
        assert client._fnos.fetch_all_pages.call_count == 2

    @patch.object(FnOS, "_refresh")
    def test_get_items_normalizes_tv_type(self, mock_refresh):
        client = FnOS.__new__(FnOS)
        client._fnos = MagicMock()
        client._play_host = "http://127.0.0.1:8003/"

        client._fnos.fetch_all_pages.return_value = [
            {
                "guid": "tv-1",
                "ancestor_guid": "lib-tv",
                "type": "TV",
                "title": "TV A",
                "air_date": "2022-06-01",
                "imdb_id": "tt456",
            },
        ]

        items = [item for item in client.get_items("lib-tv") if item]

        assert len(items) == 1
        assert items[0]["type"] == MediaType.TV.value


class TestMediaServerSync:
    """MediaServer.sync_mediaserver 应正确统计 fnOS 媒体类型."""

    @patch("app.mediaserver.media_server.get_lock_manager")
    @patch.object(MediaServer, "get_medias_count")
    @patch.object(MediaServer, "get_libraries")
    @patch.object(MediaServer, "get_items")
    @patch.object(MediaServer, "get_tv_episodes")
    def test_sync_counts_fnos_tv_and_movie(
        self,
        mock_get_tv_episodes,
        mock_get_items,
        mock_get_libraries,
        mock_get_medias_count,
        mock_get_lock_manager,
    ):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_get_lock_manager.return_value.create_lock.return_value = mock_lock

        mock_get_medias_count.return_value = {"MovieCount": 1, "SeriesCount": 1}
        mock_get_libraries.return_value = [{"id": "lib-1", "name": "综合库"}]
        mock_get_tv_episodes.return_value = [{"season_num": 1, "episode_num": 1}]

        movie_item = {
            "id": "movie-1",
            "library": "lib-1",
            "type": "Movie",
            "title": "Movie A",
        }
        tv_item = {
            "id": "tv-1",
            "library": "lib-1",
            "type": "TV",
            "title": "TV A",
        }
        mock_get_items.return_value = [movie_item, tv_item, {}]

        media_service = MagicMock()
        message = MagicMock()
        message_queue = MagicMock()
        media_sync_repo = MagicMock()
        progress = MagicMock()
        system_config = MagicMock()
        system_config.get.return_value = ["lib-1"]
        config_repo = MagicMock()

        server = MediaServer(
            media_service=media_service,
            message=message,
            message_queue=message_queue,
            media_sync_repo=media_sync_repo,
            progress_helper=progress,
            system_config=system_config,
            media_server_repo=config_repo,
        )
        server._server_type = "fnos"
        server._server = MagicMock()

        server.sync_mediaserver()

        media_sync_repo.statistics.assert_called_once()
        _, kwargs = media_sync_repo.statistics.call_args
        assert kwargs["movie_count"] == 1
        assert kwargs["tv_count"] == 1
        assert kwargs["total_count"] == 2
