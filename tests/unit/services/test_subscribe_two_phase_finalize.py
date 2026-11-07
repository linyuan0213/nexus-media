"""订阅两阶段完成回归：下载登记待转移 + 转移定稿 + 失败重开。

背景：下载阶段按真实种子清单判定覆盖并登记“待转移”（不删订阅/不写历史），
转移落盘确认后定稿（写历史、删订阅、通知），转移失败则重开订阅并复位下载历史，
既保证下载阶段判定准确，又避免转移失败被误判为已完成。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.domain.entities.rss import SubscribeState
from app.domain.media_types import ProviderMediaType
from app.events import Event
from app.events.constants import MEDIA_EPISODE_TRANSFERRED, MEDIA_TRANSFER_FINISHED, TRANSFER_FAIL
from app.events.payloads import (
    MediaEpisodeTransferredPayload,
    MediaTransferFinishedPayload,
    TransferFailPayload,
)
from app.media.models import MediaInfo
from app.services.subscribe import handlers
from app.services.subscribe.management.finish_service import SubscribeFinishService
from app.services.subscribe.management.service import SubscribeService


def _row():
    return SimpleNamespace(
        NAME="克雷瓦提斯",
        YEAR="2024",
        SEASON="2",
        TMDBID="258348",
        IMAGE="http://img",
        DESC="desc",
        TOTAL=12,
        TOTAL_EP=12,
        CURRENT_EP=1,
        OVER_EDITION=0,
        USER_ID=7,
    )


def test_finalize_tv_by_rssid_writes_history_deletes_and_notifies():
    tv_repo = MagicMock()
    tv_repo.get_all.side_effect = lambda *a, **k: [_row()] if k.get("rssid") else []
    history_repo = MagicMock()
    message = MagicMock()
    bus = MagicMock()
    svc = SubscribeFinishService(MagicMock(), tv_repo, history_repo, message, bus)
    delete_fn = MagicMock()

    svc.finalize_tv_by_rssid(5, ProviderMediaType.ANIME, delete_fn)

    history_repo.upsert.assert_called_once()
    assert history_repo.upsert.call_args.kwargs["rtype"] == "tv"
    delete_fn.assert_called_once_with(mtype=ProviderMediaType.SERIES, rssid=5)
    bus.publish.assert_called_once()
    message.send_rss_finished_message.assert_called_once()


def test_finalize_tv_anime_profile_is_persisted_to_history():
    tv_repo = MagicMock()
    row = _row()
    row.CONTENT_PROFILE = "anime"
    tv_repo.get_all.side_effect = lambda *a, **k: [row] if k.get("rssid") else []
    history_repo = MagicMock()
    svc = SubscribeFinishService(MagicMock(), tv_repo, history_repo, MagicMock(), MagicMock())

    svc.finalize_tv_by_rssid(5, ProviderMediaType.SERIES, MagicMock())

    assert history_repo.upsert.call_args.kwargs["content_profile"] == "anime"


def test_finalize_movie_by_rssid_writes_history_deletes():
    movie_repo = MagicMock()
    movie_repo.get_all.return_value = [
        SimpleNamespace(NAME="M", YEAR="2020", TMDBID="9", IMAGE="i", DESC="d", OVER_EDITION=0, USER_ID=3)
    ]
    history = MagicMock()
    message = MagicMock()
    bus = MagicMock()
    svc = SubscribeFinishService(movie_repo, MagicMock(), history, message, bus)
    delete = MagicMock()

    svc.finalize_movie_by_rssid(7, delete)

    history.upsert.assert_called_once()
    assert history.upsert.call_args.kwargs["image"] == "i"
    delete.assert_called_once_with(mtype=ProviderMediaType.MOVIE, rssid=7)
    bus.publish.assert_called_once()
    message.send_rss_finished_message.assert_called_once()
    notified = message.send_rss_finished_message.call_args.kwargs
    assert notified["owner_user_id"] == 3
    assert notified["media_info"].poster_path == "i"
    assert notified["media_info"].user_id == 3


def test_finish_rss_subscribe_captures_poster_before_delete():
    """完成通知必须在删除订阅前拿到 IMAGE，删除回调触发时媒体已带海报."""
    row = SimpleNamespace(
        NAME="M",
        YEAR="2020",
        TMDBID="9",
        IMAGE="http://poster",
        DESC="d",
        OVER_EDITION=0,
        USER_ID=3,
        CONTENT_PROFILE="demo",
    )
    movie_repo = MagicMock()
    movie_repo.get_all.return_value = [row]
    message = MagicMock()
    svc = SubscribeFinishService(movie_repo, MagicMock(), MagicMock(), message, MagicMock())
    media = MediaInfo(type=ProviderMediaType.MOVIE, tmdb_id="9")
    captured = {}

    def _delete(**kwargs):
        captured["poster"] = media.poster_path
        captured["owner"] = media.user_id

    svc.finish_rss_subscribe(7, media, _delete)

    assert captured == {"poster": "http://poster", "owner": 3}
    message.send_rss_finished_message.assert_called_once()
    assert message.send_rss_finished_message.call_args.kwargs["owner_user_id"] == 3
    assert message.send_rss_finished_message.call_args.kwargs["media_info"].content_profile == "demo"


def test_episode_transferred_finalizes_only_when_lack_empty():
    tv_repo = MagicMock()
    tv_repo.get_id.return_value = 42
    ep_repo = MagicMock()
    ep_repo.get.return_value = [1, 2, 3]
    finalize = MagicMock()
    event = Event(
        event_type=MEDIA_EPISODE_TRANSFERRED,
        payload=MediaEpisodeTransferredPayload(
            tmdb_id="1", title="T", season="1", episodes=[1, 2, 3], total_episodes=3
        ),
    )
    with (
        patch.object(handlers, "SubscribeTvRepositoryAdapter", return_value=tv_repo),
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
    ):
        handlers.handle_media_episode_transferred(event, finalize_fn=finalize)
    finalize.assert_called_once()
    assert finalize.call_args.args[0] == 42


def test_episode_transferred_uses_anchor_for_non_tmdb_subscription():
    tv_repo = MagicMock()
    tv_repo.get_id_by_anchor.return_value = 77
    ep_repo = MagicMock()
    ep_repo.get.return_value = [1]
    finalize = MagicMock()
    event = Event(
        event_type=MEDIA_EPISODE_TRANSFERRED,
        payload=MediaEpisodeTransferredPayload(
            tmdb_id="",
            title="CUSTOM-0001",
            season="1",
            episodes=[1],
            total_episodes=1,
            anchor_provider="content_id",
            anchor_external_id="CUSTOM-0001",
            content_profile="custom",
            user_id=3,
        ),
    )
    with (
        patch.object(handlers, "SubscribeTvRepositoryAdapter", return_value=tv_repo),
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
    ):
        handlers.handle_media_episode_transferred(event, finalize_fn=finalize)

    tv_repo.get_id_by_anchor.assert_called_once_with(
        "content_id",
        "CUSTOM-0001",
        season="1",
        content_profile="custom",
        user_id=3,
    )
    tv_repo.get_id.assert_not_called()
    finalize.assert_called_once()
    assert finalize.call_args.args[0] == 77


def test_episode_transferred_partial_does_not_finalize():
    tv_repo = MagicMock()
    tv_repo.get_id.return_value = 42
    ep_repo = MagicMock()
    ep_repo.get.return_value = [1, 2, 3, 4, 5]
    finalize = MagicMock()
    event = Event(
        event_type=MEDIA_EPISODE_TRANSFERRED,
        payload=MediaEpisodeTransferredPayload(tmdb_id="1", title="T", season="1", episodes=[1], total_episodes=5),
    )
    with (
        patch.object(handlers, "SubscribeTvRepositoryAdapter", return_value=tv_repo),
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
    ):
        handlers.handle_media_episode_transferred(event, finalize_fn=finalize)
    finalize.assert_not_called()
    tv_repo.update_lack.assert_called_once()


def test_pending_subscription_not_reopened_on_partial_transfer():
    """待转移(COMPLETED)订阅在分批转移期间保持完成态，避免被 RSS 重新匹配重复下载。"""
    tv_repo = MagicMock()
    tv_repo.get_id.return_value = 42
    tv_repo.get_all.return_value = [SimpleNamespace(state=SubscribeState.COMPLETED.value)]
    ep_repo = MagicMock()
    ep_repo.get.return_value = [1, 2, 3, 4, 5]
    event = Event(
        event_type=MEDIA_EPISODE_TRANSFERRED,
        payload=MediaEpisodeTransferredPayload(tmdb_id="1", title="T", season="1", episodes=[1], total_episodes=5),
    )
    with (
        patch.object(handlers, "SubscribeTvRepositoryAdapter", return_value=tv_repo),
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
    ):
        handlers.handle_media_episode_transferred(event)

    tv_repo.update_state.assert_not_called()
    tv_repo.update_lack.assert_called_once()


def test_transfer_fail_reopens_subscription_and_resets_history():
    svc = MagicMock()
    handler = handlers.build_transfer_fail_reopen_handler(svc)
    history = SimpleNamespace(tmdb_id="123", season_episode="S01E05", downloader="qb", download_id="t1")
    sub = SimpleNamespace(tmdb_id="123", season="1", id=9)
    ep_repo = MagicMock()
    ep_repo.get.return_value = [7]
    event = Event(event_type=TRANSFER_FAIL, payload=TransferFailPayload(path="/dl/x", count=1, reason="boom"))

    with (
        patch.object(handlers, "DownloadHistoryRepositoryAdapter") as dha,
        patch.object(handlers, "SubscribeTvRepositoryAdapter") as tha,
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
        patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra,
        patch.object(handlers, "RegexParser") as rp,
    ):
        dha.return_value.get_by_path.return_value = history
        tha.return_value.get_all.return_value = [sub]
        mra.return_value.get_all.return_value = []
        rp.return_value.parse.return_value = SimpleNamespace(season=1, episode=5, end_episode=6)
        handler(event)

    svc.update_rss_state.assert_called_once_with(ProviderMediaType.SERIES, 9, SubscribeState.RUNNING.value)
    # 失败集 5-6 回补缺失（已有 7）
    tha.return_value.update_lack.assert_called_once_with(
        title=None, year=None, season=None, rssid=9, lack_episodes=[5, 6, 7]
    )
    dha.return_value.update_state.assert_called_once_with("qb", "t1", "downloading")


def test_transfer_fail_reopens_tv_subscription_by_anchor():
    """多元数据 TV 订阅无 TMDB，失败时按锚点回补缺失."""
    svc = MagicMock()
    handler = handlers.build_transfer_fail_reopen_handler(svc)
    history = SimpleNamespace(
        tmdb_id="",
        anchor_provider="content_id",
        anchor_external_id="CUSTOM-0001",
        season_episode="S01E01",
        downloader="qb",
        download_id="t3",
    )
    sub = SimpleNamespace(
        id=12,
        tmdb_id="",
        anchor_provider="content_id",
        anchor_external_id="CUSTOM-0001",
        season="1",
        user_id=None,
    )
    ep_repo = MagicMock()
    ep_repo.get.return_value = []
    event = Event(event_type=TRANSFER_FAIL, payload=TransferFailPayload(path="/dl/x", count=1, reason="boom"))

    with (
        patch.object(handlers, "DownloadHistoryRepositoryAdapter") as dha,
        patch.object(handlers, "SubscribeTvRepositoryAdapter") as tha,
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter", return_value=ep_repo),
        patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra,
        patch.object(handlers, "RegexParser") as rp,
    ):
        dha.return_value.get_by_path.return_value = history
        tha.return_value.get_all.return_value = [sub]
        mra.return_value.get_all.return_value = []
        rp.return_value.parse.return_value = SimpleNamespace(season=1, episode=1, end_episode=None)
        handler(event)

    svc.update_rss_state.assert_called_once_with(ProviderMediaType.SERIES, 12, SubscribeState.RUNNING.value)
    tha.return_value.update_lack.assert_called_once_with(
        title=None, year=None, season=None, rssid=12, lack_episodes=[1]
    )


def test_transfer_fail_reopens_movie_subscription():
    svc = MagicMock()
    handler = handlers.build_transfer_fail_reopen_handler(svc)
    history = SimpleNamespace(tmdb_id="55", season_episode="", downloader="qb", download_id="t2")
    movie = SimpleNamespace(id=11, tmdb_id="55")
    event = Event(event_type=TRANSFER_FAIL, payload=TransferFailPayload(path="/dl/m", count=1, reason="boom"))

    with (
        patch.object(handlers, "DownloadHistoryRepositoryAdapter") as dha,
        patch.object(handlers, "SubscribeTvRepositoryAdapter") as tha,
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter"),
        patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra,
        patch.object(handlers, "RegexParser") as rp,
    ):
        dha.return_value.get_by_path.return_value = history
        tha.return_value.get_all.return_value = []
        mra.return_value.get_all.return_value = [movie]
        rp.return_value.parse.return_value = SimpleNamespace(season=None, episode=None, end_episode=None)
        handler(event)

    svc.update_rss_state.assert_called_once_with(ProviderMediaType.MOVIE, 11, SubscribeState.RUNNING.value)


def test_transfer_fail_reopens_movie_subscription_by_anchor():
    """自定义画像电影无 TMDB，失败时按锚点重开订阅."""
    svc = MagicMock()
    handler = handlers.build_transfer_fail_reopen_handler(svc)
    history = SimpleNamespace(
        tmdb_id="",
        anchor_provider="demo",
        anchor_external_id="ABC-123",
        season_episode="",
        downloader="qb",
        download_id="t3",
    )
    movie = SimpleNamespace(
        id=12,
        tmdb_id="",
        provider="aggregate",
        anchor_provider="demo",
        anchor_external_id="ABC-123",
    )
    event = Event(event_type=TRANSFER_FAIL, payload=TransferFailPayload(path="/dl/m", count=1, reason="boom"))

    with (
        patch.object(handlers, "DownloadHistoryRepositoryAdapter") as dha,
        patch.object(handlers, "SubscribeTvRepositoryAdapter") as tha,
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter"),
        patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra,
        patch.object(handlers, "RegexParser") as rp,
    ):
        dha.return_value.get_by_path.return_value = history
        tha.return_value.get_all.return_value = []
        mra.return_value.get_all.return_value = [movie]
        rp.return_value.parse.return_value = SimpleNamespace(season=None, episode=None, end_episode=None)
        handler(event)

    svc.update_rss_state.assert_called_once_with(ProviderMediaType.MOVIE, 12, SubscribeState.RUNNING.value)


def test_movie_transfer_finished_finalizes_movie_subscription():
    svc = MagicMock()
    handler = handlers.build_movie_transfer_finalize_handler(svc)
    sub = SimpleNamespace(id=11, tmdb_id="55")
    event = Event(
        event_type=MEDIA_TRANSFER_FINISHED,
        payload=MediaTransferFinishedPayload(
            in_path=None,
            file=None,
            target_path=None,
            dest=None,
            media_info={"type": ProviderMediaType.MOVIE.value, "tmdb_id": "55"},
        ),
    )
    with patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra:
        mra.return_value.get_all.return_value = [sub]
        handler(event)

    svc.finalize_movie_by_rssid.assert_called_once_with(11)


def test_movie_transfer_finished_finalizes_by_anchor_when_provider_is_aggregate():
    """虚拟聚合源订阅按锚点定稿，provider 聚合名不参与真实来源比对."""
    svc = MagicMock()
    handler = handlers.build_movie_transfer_finalize_handler(svc)
    sub = SimpleNamespace(
        id=13,
        tmdb_id="",
        provider="aggregate",
        anchor_provider="demo",
        anchor_external_id="ABC-123",
    )
    event = Event(
        event_type=MEDIA_TRANSFER_FINISHED,
        payload=MediaTransferFinishedPayload(
            in_path=None,
            file=None,
            target_path=None,
            dest=None,
            media_info={
                "type": ProviderMediaType.MOVIE.value,
                "content_profile": "custom",
                "anchor_provider": "demo",
                "anchor_external_id": "ABC-123",
            },
        ),
    )
    with patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra:
        mra.return_value.get_all.return_value = [sub]
        handler(event)

    svc.finalize_movie_by_rssid.assert_called_once_with(13)


def test_movie_transfer_finished_finalizes_once_for_duplicate_rows():
    """同一电影的重复订阅行只定稿一次，避免重复写历史/通知."""
    svc = MagicMock()
    handler = handlers.build_movie_transfer_finalize_handler(svc)
    event = Event(
        event_type=MEDIA_TRANSFER_FINISHED,
        payload=MediaTransferFinishedPayload(
            in_path=None,
            file=None,
            target_path=None,
            dest=None,
            media_info={"type": ProviderMediaType.MOVIE.value, "tmdb_id": "55"},
        ),
    )
    with patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra:
        mra.return_value.get_all.return_value = [
            SimpleNamespace(id=11, tmdb_id="55"),
            SimpleNamespace(id=11, tmdb_id="55"),
        ]
        handler(event)

    svc.finalize_movie_by_rssid.assert_called_once_with(11)


def test_movie_transfer_finished_ignores_tv():
    svc = MagicMock()
    handler = handlers.build_movie_transfer_finalize_handler(svc)
    event = Event(
        event_type=MEDIA_TRANSFER_FINISHED,
        payload=MediaTransferFinishedPayload(
            in_path=None,
            file=None,
            target_path=None,
            dest=None,
            media_info={"type": ProviderMediaType.SERIES.value, "tmdb_id": "55"},
        ),
    )
    with patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra:
        handler(event)

    mra.assert_not_called()
    svc.finalize_movie_by_rssid.assert_not_called()


def test_transfer_fail_reopen_scoped_to_owner():
    """仅回滚失败下载归属用户的订阅，不波及同媒体其他用户。"""
    svc = MagicMock()
    handler = handlers.build_transfer_fail_reopen_handler(svc)
    history = SimpleNamespace(tmdb_id="123", season_episode="", downloader="qb", download_id="t1", user_id=3)
    subs = [
        SimpleNamespace(id=9, tmdb_id="123", season="1", user_id=3),
        SimpleNamespace(id=10, tmdb_id="123", season="1", user_id=4),
    ]
    event = Event(event_type=TRANSFER_FAIL, payload=TransferFailPayload(path="/dl/x", count=1, reason="boom"))

    with (
        patch.object(handlers, "DownloadHistoryRepositoryAdapter") as dha,
        patch.object(handlers, "SubscribeTvRepositoryAdapter") as tha,
        patch.object(handlers, "SubscribeTvEpisodeRepositoryAdapter"),
        patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra,
        patch.object(handlers, "RegexParser") as rp,
    ):
        dha.return_value.get_by_path.return_value = history
        tha.return_value.get_all.return_value = subs
        mra.return_value.get_all.return_value = []
        rp.return_value.parse.return_value = SimpleNamespace(season=None, episode=None, end_episode=None)
        handler(event)

    svc.update_rss_state.assert_called_once_with(ProviderMediaType.SERIES, 9, SubscribeState.RUNNING.value)


def test_movie_transfer_finished_skips_when_not_in_library():
    """电影未入库（如附加文件先落盘）时不定稿。"""
    svc = MagicMock()
    svc.media_exists.return_value = False
    handler = handlers.build_movie_transfer_finalize_handler(svc)
    event = Event(
        event_type=MEDIA_TRANSFER_FINISHED,
        payload=MediaTransferFinishedPayload(
            in_path=None,
            file=None,
            target_path=None,
            dest=None,
            media_info={"type": ProviderMediaType.MOVIE.value, "tmdb_id": "55", "title": "M", "year": "2020"},
        ),
    )
    with patch.object(handlers, "SubscribeMovieRepositoryAdapter") as mra:
        mra.return_value.get_all.return_value = [SimpleNamespace(id=11, tmdb_id="55")]
        handler(event)

    svc.finalize_movie_by_rssid.assert_not_called()


def _svc_for_reconcile():
    svc = SubscribeService.__new__(SubscribeService)
    svc._tv_repo = MagicMock()
    svc._movie_repo = MagicMock()
    svc._download_repo = None
    final_tv = MagicMock()
    final_mv = MagicMock()
    reopen = MagicMock()
    setattr(svc, "finalize_tv_by_rssid", final_tv)
    setattr(svc, "finalize_movie_by_rssid", final_mv)
    setattr(svc, "update_rss_state", reopen)
    return svc, final_tv, final_mv, reopen


def test_reconcile_finalizes_when_library_has_media():
    import datetime

    svc, final_tv, _final_mv, reopen = _svc_for_reconcile()
    tv = SimpleNamespace(id=5, name="T", year="2024", season="1", total=12, tmdb_id="1")
    svc._tv_repo.get_all.return_value = [tv]
    svc._movie_repo.get_all.return_value = []
    setattr(svc, "media_exists", MagicMock(return_value=True))

    svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_tv.assert_called_once_with(5, ProviderMediaType.SERIES)
    reopen.assert_not_called()


def test_reconcile_reopens_stale_pending():
    import datetime

    svc, final_tv, _final_mv, reopen = _svc_for_reconcile()
    tv = SimpleNamespace(id=5, name="T", year="2024", season="1", total=12, tmdb_id="1")
    svc._tv_repo.get_all.return_value = [tv]
    svc._movie_repo.get_all.return_value = []
    setattr(svc, "media_exists", MagicMock(return_value=False))
    svc._download_repo = MagicMock()
    svc._download_repo.get_by_tmdb.return_value = [SimpleNamespace(tmdb_id="1", date="2020-01-01 00:00:00")]

    svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_tv.assert_not_called()
    reopen.assert_called_once_with(ProviderMediaType.SERIES, 5, SubscribeState.RUNNING.value)


def test_reconcile_finalizes_anime_tv_with_anime_type():
    import datetime

    svc, final_tv, _final_mv, reopen = _svc_for_reconcile()
    tv = SimpleNamespace(id=5, name="T", year="2024", season="1", total=12, tmdb_id="1", content_profile="anime")
    svc._tv_repo.get_all.return_value = [tv]
    svc._movie_repo.get_all.return_value = []
    setattr(svc, "media_exists", MagicMock(return_value=True))

    svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_tv.assert_called_once_with(5, ProviderMediaType.ANIME)
    reopen.assert_not_called()


def test_reconcile_reopens_stale_movie_pending_by_anchor():
    """无 TMDB 的自定义画像电影待转移超时后按锚点重开."""
    import datetime

    svc, _final_tv, _final_mv, reopen = _svc_for_reconcile()
    movie = SimpleNamespace(
        id=12,
        name="ABC-123",
        year="2024",
        tmdb_id="",
        identity_id="id-1",
        anchor_provider="demo",
        anchor_external_id="ABC-123",
        content_profile="custom",
        keyword="ABC-123",
    )
    svc._tv_repo.get_all.return_value = []
    svc._movie_repo.get_all.return_value = [movie]
    setattr(svc, "media_exists", MagicMock(return_value=False))
    svc._download_repo = MagicMock()
    svc._download_repo.get_by_identity.return_value = [SimpleNamespace(identity_id="id-1", date="2020-01-01 00:00:00")]

    svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    svc._download_repo.get_by_identity.assert_called_once_with(
        identity_id="id-1", anchor_provider="demo", anchor_external_id="ABC-123"
    )
    reopen.assert_called_once_with(ProviderMediaType.MOVIE, 12, SubscribeState.RUNNING.value)


def test_reconcile_leaves_fresh_pending():
    import datetime

    svc, final_tv, _final_mv, reopen = _svc_for_reconcile()
    tv = SimpleNamespace(id=5, name="T", year="2024", season="1", total=12, tmdb_id="1")
    svc._tv_repo.get_all.return_value = [tv]
    svc._movie_repo.get_all.return_value = []
    setattr(svc, "media_exists", MagicMock(return_value=False))
    svc._download_repo = MagicMock()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    svc._download_repo.get_by_tmdb.return_value = [
        SimpleNamespace(tmdb_id="1", date=(now - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
    ]

    svc.reconcile_pending_transfers(now=now)

    reopen.assert_not_called()
    final_tv.assert_not_called()


def test_reconcile_finalizes_running_movie_when_transfer_history_exists():
    """转移成功优先于订阅 STATE；历史 R 状态也应直接定稿."""
    import datetime
    from unittest.mock import patch

    svc, _final_tv, final_mv, reopen = _svc_for_reconcile()
    movie = SimpleNamespace(
        id=21,
        name="PRWF-017",
        year="",
        tmdb_id="",
        state="R",
        identity_id="id-21",
        anchor_provider="demo_meta",
        anchor_external_id="PRWF-017",
        content_profile="custom",
        keyword="PRWF-017",
    )
    svc._tv_repo.get_all.return_value = []
    svc._movie_repo.get_all.return_value = [movie]
    transfer_repo = MagicMock()
    transfer_repo.return_value.get_existing_anchors.return_value = {("demo_meta", "PRWF-017")}

    with patch("app.services.subscribe.management.service.TransferRepository", transfer_repo):
        svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_mv.assert_called_once_with(21)
    reopen.assert_not_called()


def test_reconcile_does_not_finalize_over_edition_movie_from_old_transfer():
    """洗版订阅有旧转移历史时仍应继续搜索/下载，不能立即定稿."""
    import datetime
    from unittest.mock import patch

    svc, _final_tv, final_mv, reopen = _svc_for_reconcile()
    movie = SimpleNamespace(
        id=23,
        name="ABC-123",
        year="",
        tmdb_id="",
        state="R",
        over_edition=True,
        identity_id="id-23",
        anchor_provider="demo",
        anchor_external_id="ABC-123",
    )
    svc._tv_repo.get_all.return_value = []
    svc._movie_repo.get_all.return_value = [movie]
    transfer_repo = MagicMock()
    transfer_repo.return_value.get_existing_anchors.return_value = {("demo", "ABC-123")}
    transfer_repo.return_value.get_existing_external_ids.return_value = {"ABC-123"}
    setattr(svc, "media_exists", MagicMock(return_value=False))

    with patch("app.services.subscribe.management.service.TransferRepository", transfer_repo):
        svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_mv.assert_not_called()


def test_reconcile_normalizes_content_id_prefixed_anchor():
    """订阅锚点被写成 tmdb:content_id:XXX 时，也应按外部 ID 命中转移历史."""
    import datetime
    from unittest.mock import patch

    svc, _final_tv, final_mv, reopen = _svc_for_reconcile()
    movie = SimpleNamespace(
        id=22,
        name="ABC-123",
        year="",
        tmdb_id="",
        state="C",
        identity_id="id-22",
        anchor_provider="tmdb",
        anchor_external_id="content_id:ABC-123",
        content_profile="custom",
        keyword="ABC-123",
    )
    svc._tv_repo.get_all.return_value = []
    svc._movie_repo.get_all.return_value = [movie]
    transfer_repo = MagicMock()
    transfer_repo.return_value.get_existing_anchors.return_value = set()
    transfer_repo.return_value.get_existing_external_ids.return_value = {"ABC-123"}

    with patch("app.services.subscribe.management.service.TransferRepository", transfer_repo):
        svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    transfer_repo.return_value.get_existing_external_ids.assert_called_once_with(["ABC-123"])
    final_mv.assert_called_once_with(22)
    reopen.assert_not_called()


def test_reconcile_handles_season_string_prefix():
    """SEASON 存 "S02" 时不能因 int("S02") 异常跳过定稿."""
    import datetime

    svc, final_tv, _final_mv, reopen = _svc_for_reconcile()
    tv = SimpleNamespace(id=43, name="Anime", year="2022", season="S02", total=10, tmdb_id="105248")
    svc._tv_repo.get_all.return_value = [tv]
    svc._movie_repo.get_all.return_value = []
    setattr(svc, "media_exists", MagicMock(return_value=True))

    svc.reconcile_pending_transfers(now=datetime.datetime(2026, 1, 1))

    final_tv.assert_called_once_with(43, ProviderMediaType.SERIES)
    reopen.assert_not_called()
