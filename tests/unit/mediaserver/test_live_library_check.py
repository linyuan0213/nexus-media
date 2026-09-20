"""媒体服务器实时库存在性检查（"已入库"标识的兜底）测试."""

from unittest.mock import MagicMock

from app.mediaserver.media_server import MediaServer


def _facade(server):
    """构造最小 facade：server 为只读属性，直接设置底层 _server/_server_type."""
    ms = MediaServer.__new__(MediaServer)
    ms._server = server
    ms._server_type = "emby" if server is not None else None
    ms.config_repo = None
    return ms


def test_movie_present_and_cached():
    server = MagicMock()
    server.get_movies.return_value = [{"title": "x", "year": "2026"}]
    ms = _facade(server)

    assert ms.check_library_present("movie", "穹庐下的魔女", "2026") is True
    # 命中缓存后不再请求媒体服务器
    assert ms.check_library_present("movie", "穹庐下的魔女", "2026") is True
    server.get_movies.assert_called_once()


def test_movie_absent():
    server = MagicMock()
    server.get_movies.return_value = []
    ms = _facade(server)
    assert ms.check_library_present("movie", "不存在的电影", "1999") is False


def test_tv_present_uses_series_lookup():
    server = MagicMock()
    server.get_tv_episodes.return_value = [{"id": "e1"}]
    ms = _facade(server)

    assert ms.check_library_present("tv", "穹庐下的魔女", "2026", tmdbid="DB:37315819") is True
    assert server.get_tv_episodes.call_args.kwargs["tmdbid"] is None  # 非数字 id 不透传


def test_no_server_returns_false():
    assert _facade(None).check_library_present("tv", "x", "2026") is False
