"""媒体服务器相关插件的多实例路由测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins._ms_common.mediaserver_lifecycle import resolve_plugin_server_id
from app.plugin_framework.builtin_plugins.libraryrefresh.backend.plugin import LibraryRefreshPlugin
from app.plugin_framework.builtin_plugins.movielike.backend.plugin import MovieLikePlugin
from app.plugin_framework.builtin_plugins.speedlimiter.backend.plugin import SpeedLimiterPlugin


def test_libraryrefresh_root_refresh_uses_directory_target():
    plugin = LibraryRefreshPlugin.__new__(LibraryRefreshPlugin)
    plugin.ctx = MagicMock()
    plugin._mediaserver = MagicMock()
    plugin._mediaserver.resolve_route.return_value = SimpleNamespace(server_id=2, library_id="4")
    plugin._mediaserver.get_type.return_value = "emby"

    plugin._refresh_library({"dest": "/media/demo/movie", "media_info": {}})

    plugin._mediaserver.resolve_route.assert_called_once_with(None, "/media/demo/movie")
    plugin._mediaserver.refresh_root_library.assert_called_once_with(server_id=2, library_id="4")


def test_libraryrefresh_media_event_also_scans_routed_library():
    plugin = LibraryRefreshPlugin.__new__(LibraryRefreshPlugin)
    plugin.ctx = MagicMock()
    plugin._mediaserver = MagicMock()
    plugin._mediaserver.resolve_route.return_value = SimpleNamespace(server_id=2, library_id="4")
    plugin._mediaserver.get_type.return_value = "emby"

    plugin._refresh_library(
        {
            "dest": "/media/private/movie",
            "media_info": {"title": "PPR-012", "year": "2026", "content_profile": "private"},
        }
    )

    plugin._mediaserver.refresh_library_with_scan.assert_called_once()


def test_movielike_uses_directory_routed_server_type():
    plugin = MovieLikePlugin.__new__(MovieLikePlugin)
    plugin.ctx = MagicMock()
    plugin._mediaserver = MagicMock()
    plugin._mediaserver.resolve_server_id.return_value = 2
    plugin._mediaserver.get_type.return_value = "jellyfin"
    plugin._get_config = MagicMock(return_value={"enable": True})

    with patch("app.plugin_framework.builtin_plugins.movielike.backend.plugin.update_favtype"):
        plugin._fav_transfer(
            {
                "Event": "item.rate",
                "Item": {"Type": "Movie", "Path": "/media/demo/movie/file.mkv"},
            }
        )

    plugin._mediaserver.get_type.assert_called_once_with(2)


def test_speedlimiter_aggregates_sessions_from_multiple_instances():
    plugin = SpeedLimiterPlugin.__new__(SpeedLimiterPlugin)
    plugin.ctx = MagicMock()
    plugin._mediaserver = MagicMock()
    plugin._mediaserver.get_type.return_value = "emby"
    plugin._mediaserver.get_playing_sessions.side_effect = lambda server_id: [
        {"NowPlayingItem": {"MediaType": "Video", "Bitrate": 100}}
    ]
    plugin._get_config = MagicMock(return_value={"server_ids": ["1", "2"]})
    plugin._unlimited_ips = {}
    plugin._auto_limit = True
    plugin._playing_flag = False
    plugin._calc_limit = MagicMock()
    plugin._check_limited_downloader = MagicMock(return_value=([], ""))

    with patch(
        "app.plugin_framework.builtin_plugins.speedlimiter.backend.plugin.SecurityChecker.allow_access",
        return_value=False,
    ):
        plugin._check_playing_sessions()

    assert plugin._mediaserver.get_playing_sessions.call_count == 2
    plugin._calc_limit.assert_called_once_with(200)


def test_plugin_server_id_accepts_string_and_falls_back_to_route():
    media_server = MagicMock()
    media_server.resolve_server_id.return_value = 3
    assert resolve_plugin_server_id(media_server, {"server_id": "3"}) == 3
    media_server.resolve_server_id.assert_called_with(3, None, None)
