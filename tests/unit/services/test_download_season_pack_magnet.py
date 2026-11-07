"""磁力整季包：加入后读取文件清单筛选取需，失败回滚（原子化）。"""

from unittest.mock import MagicMock

from app.domain.media_types import ProviderMediaType
from app.services import download_strategies
from app.services.download_strategies import EpisodeStrategy


def _item(episodes):
    item = MagicMock()
    item.type = ProviderMediaType.SERIES
    item.tmdb_id = 1
    item.enclosure = "magnet:?xt=urn:btih:abc"
    item.page_url = "http://p"
    item.org_string = "Show S01"
    item.get_season_list.return_value = [1]
    item.get_episode_list.return_value = episodes
    return item


def _run(monkeypatch, item, by_tid_episodes):
    monkeypatch.setattr(download_strategies, "is_download_failed", lambda i: False)
    download_callback = MagicMock(return_value=("qb", "id1", ""))
    set_status = MagicMock()
    start = MagicMock()
    remove = MagicMock()
    get_by_tid = MagicMock(return_value=by_tid_episodes)
    need_tvs = {1: [{"season": 1, "episodes": [1, 2]}]}
    items, need = EpisodeStrategy.download_from_season_pack(
        download_list=[item],
        need_tvs=need_tvs,
        get_download_url_callback=MagicMock(return_value="http://dl"),
        download_callback=download_callback,
        get_torrent_episodes_callback=MagicMock(return_value=([], None)),
        set_files_status_callback=set_status,
        start_torrents_callback=start,
        return_items=[],
        get_torrent_episodes_by_tid_callback=get_by_tid,
        remove_torrents_callback=remove,
    )
    return items, need, download_callback, set_status, start, remove, get_by_tid


def test_magnet_season_pack_selects_needed(monkeypatch):
    items, need, download_callback, set_status, start, remove, get_by_tid = _run(
        monkeypatch, _item([1, 2, 3]), [1, 2, 3]
    )
    download_callback.assert_called_once()
    assert download_callback.call_args.kwargs.get("is_paused") is True
    get_by_tid.assert_called_once()
    set_status.assert_called_once()
    start.assert_called_once()
    remove.assert_not_called()
    assert len(items) == 1
    assert need == {}


def test_magnet_season_pack_rolls_back_when_no_needed(monkeypatch):
    items, need, download_callback, set_status, start, remove, _get_by_tid = _run(
        monkeypatch, _item([1, 2, 3]), [9, 10]
    )
    download_callback.assert_called_once()
    remove.assert_called_once()
    start.assert_not_called()
    set_status.assert_not_called()
    assert items == []
