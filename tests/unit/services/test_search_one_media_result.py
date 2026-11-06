"""Searcher.search_one_media 返回值语义 — 电影不应把"其它候选未下载"当成无结果."""

from unittest.mock import MagicMock, patch

from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.search_service import Searcher, SearchQueryBuilder, SearchResultProcessor


def _make_searcher() -> Searcher:
    message = MagicMock()
    message.get_search_types.return_value = []
    searcher = Searcher(
        download_repo=MagicMock(),
        search_repo=MagicMock(),
        downloader=MagicMock(),
        media_service=MagicMock(),
        message=message,
        progress_helper=MagicMock(),
        indexer_service=MagicMock(),
        event_bus=MagicMock(),
    )
    return searcher


class TestSearchOneMediaReturn:
    """电影：即使还有其它候选未下载，也应返回已下载项（供订阅判定完成）."""

    def _run(self, media_type: MediaType):
        searcher = _make_searcher()
        downloaded = MagicMock(name="downloaded")
        leftover = MagicMock(name="leftover")
        media = MediaInfo(title="年会不能停2", type=media_type, year="2026", tmdb_id=123)

        with (
            patch.object(SearchQueryBuilder, "build_search_names", return_value=(["年会不能停2"], 1)),
            patch("app.services.search_service.SearchExecutor") as executor_cls,
            patch("app.services.search_service.SearchResultDeduplicator") as dedup_cls,
            patch("app.services.search_service.SearchResultProcessor") as processor_cls,
        ):
            executor_cls.return_value.execute.return_value = [downloaded, leftover]
            dedup_cls.deduplicate.side_effect = lambda items: items
            processor = processor_cls.return_value
            processor.filter_downloaded.return_value = [downloaded, leftover]
            processor.batch_download.return_value = ([downloaded], [leftover])

            result = searcher.search_one_media(media, SearchType.SUBSCRIBE, {})

        return result, downloaded

    def test_movie_returns_downloaded_item_with_leftovers(self):
        (first, _no_exists, _total, download_count), downloaded = self._run(MediaType.MOVIE)
        assert first is downloaded
        assert download_count == 1

    def test_tv_still_returns_none_with_leftovers(self):
        (first, _no_exists, _total, download_count), _downloaded = self._run(MediaType.TV)
        assert first is None
        assert download_count == 1


class TestCustomProfileSearchNames:
    """自定义画像只用内容编号搜索，不叠加标题."""

    def test_custom_profile_returns_keyword_only(self):
        media = MediaInfo(
            title="演示内容 DEMO-660",
            type=MediaType.MOVIE,
            year="2026",
            tmdb_id="content_id:DEMO-660",
            keyword="DEMO-660",
            content_profile="demo",
        )

        names, workers = SearchQueryBuilder.build_search_names(media, MagicMock())

        assert names == ["DEMO-660"]
        assert workers == 1

    def test_fill_missing_episode_from_raw_title(self):
        media = MediaInfo(
            title="学生会也有洞！",
            type=MediaType.ANIME,
            org_string=(
                "[绿茶字幕组&LoliHouse] 学生会也有洞！ / Seitokai ni mo Ana wa Aru "
                "- 01 [WebRip 1080p HEVC-10bit AAC][简繁日内封字幕]"
            ),
        )
        SearchResultProcessor.fill_missing_episode(media)
        assert media.begin_episode == 1
        assert media.get_season_episode_string() == "S01 E01"

    def test_fill_missing_episode_supports_chinese_episode(self):
        media = MediaInfo(title="某番", type=MediaType.ANIME, org_string="某番 第8集 1080P")
        SearchResultProcessor.fill_missing_episode(media)
        assert media.begin_episode == 8
        assert media.get_season_episode_string() == "S01 E08"

    def test_fill_missing_episode_skips_multi_episode_pack(self):
        media = MediaInfo(title="某番", type=MediaType.ANIME, org_string="某番 01-12 1080P")
        SearchResultProcessor.fill_missing_episode(media)
        assert media.begin_episode is None

        media_with_total = MediaInfo(
            title="某番",
            type=MediaType.ANIME,
            org_string="某番 全集 1080P",
            total_episodes=12,
        )
        SearchResultProcessor.fill_missing_episode(media_with_total)
        assert media_with_total.begin_episode is None

    def test_movie_ignores_numeric_tmdb_keyword(self):
        media = MediaInfo(
            title="搏击俱乐部",
            cn_name="搏击俱乐部",
            type=MediaType.MOVIE,
            content_profile="movie",
            keyword="550",
            tmdb_id=550,
        )
        names, _ = SearchQueryBuilder.build_search_names(media, MagicMock())

        assert "550" not in names
        assert "搏击俱乐部" in names

    def test_anime_profile_ignores_numeric_tmdb_keyword(self):
        media = MediaInfo(
            title="学生会也有洞！",
            cn_name="学生会也有洞！",
            type=MediaType.ANIME,
            content_profile="anime",
            keyword="283938",
            tmdb_id=283938,
        )
        names, _ = SearchQueryBuilder.build_search_names(media, MagicMock())

        assert "283938" not in names
        assert "学生会也有洞！" in names


def test_build_search_names_uses_persisted_aliases_without_provider_call():
    gateway = MagicMock()
    media = MediaInfo(
        title="学生会也有洞！",
        cn_name="学生会也有洞！",
        original_title="生徒会にも穴はある!",
        original_language="ja",
        type=MediaType.ANIME,
        aliases=["Seitokai ni mo Ana wa Aru!", "學生會也有洞！"],
    )
    names, _ = SearchQueryBuilder.build_search_names(media, gateway)
    assert "Seitokai ni mo Ana wa Aru!" in names
    assert "學生會也有洞！" in names
    gateway.en_title.assert_not_called()
    gateway.zhtw_title.assert_not_called()
