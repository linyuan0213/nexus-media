"""媒体库 ID 定向刷新测试。"""

from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.mediaserver.client.emby import Emby
from app.mediaserver.client.fnos import FnOS
from app.mediaserver.client.jellyfin import Jellyfin
from app.mediaserver.client.plex import Plex
from app.mediaserver.media_server import MediaServer


def test_emby_item_honors_explicit_library_id():
    client = Emby.__new__(Emby)
    assert cast(Any, client)._Emby__get_emby_library_id_by_item({"library_id": "4"}) == "4"


def test_emby_refresh_uses_path_when_title_does_not_match():
    client = Emby.__new__(Emby)
    client._host = "http://emby/"
    client._apikey = "key"
    client.get_movies = MagicMock(return_value=[])
    client.get_item_id_by_path = MagicMock(return_value="129531")
    refresh_item = MagicMock()
    setattr(client, "_Emby__refresh_emby_library_by_id", refresh_item)

    client.refresh_library_by_items(
        [
            {
                "title": "TC-268 アダルト動画サイト MGS動画",
                "year": "",
                "type": "movie",
                "file_path": "/Media/demo/日本有码/TC/TC-268/TC-268.mp4",
            }
        ]
    )

    client.get_item_id_by_path.assert_called_once_with("/Media/demo/日本有码/TC/TC-268/TC-268.mp4")
    refresh_item.assert_called_once_with("129531", replace_images=False)


def test_root_refresh_uses_library_id_when_supported():
    server = MediaServer.__new__(MediaServer)
    client = MagicMock()
    server._get_client = MagicMock(return_value=client)

    server.refresh_root_library(server_id=2, library_id="4")

    client.refresh_library.assert_called_once_with("4")
    client.refresh_root_library.assert_not_called()


def test_fnos_refresh_by_items_uses_library_guid():
    client = FnOS.__new__(FnOS)
    client._fnos = MagicMock()
    client.refresh_root_library = MagicMock()
    client.refresh_library_by_items([{"library_id": "guid-1"}])
    client._fnos.refresh_library.assert_called_once_with("guid-1")
    client.refresh_root_library.assert_not_called()


def test_jellyfin_refresh_by_items_uses_library_id():
    client = Jellyfin.__new__(Jellyfin)
    client._host = "http://jellyfin/"
    client._apikey = "key"
    client._auth_headers = MagicMock(return_value={})
    client.refresh_root_library = MagicMock()
    with patch("app.mediaserver.client.jellyfin.HttpClient") as http_client:
        http_client.return_value.post.return_value = MagicMock()
        client.refresh_library_by_items([{"library_id": "lib-1"}])
    request_url = http_client.return_value.post.call_args.args[0]
    assert "Items/lib-1/Refresh" in request_url
    client.refresh_root_library.assert_not_called()


def test_plex_refresh_by_items_uses_section_id():
    client = Plex.__new__(Plex)
    client._plex = MagicMock()
    client._plex.library.sections.return_value = []
    client.refresh_library_by_items([{"library_id": "7"}])
    client._plex.query.assert_called_once_with("/library/sections/7/refresh")


def test_emby_item_refresh_never_replace_all_images():
    client = Emby.__new__(Emby)
    client._host = "http://emby/"
    client._apikey = "key"
    with patch("app.mediaserver.client.emby.HttpClient") as http_client:
        http_client.return_value.post.return_value = MagicMock()
        getattr(client, "_Emby__refresh_emby_library_by_id")("129531", replace_images=False)
    request_url = http_client.return_value.post.call_args.args[0]
    assert "ImageRefreshMode=FullRefresh" in request_url
    assert "ReplaceAllImages=false" in request_url
    assert "ReplaceAllImages=true" not in request_url
