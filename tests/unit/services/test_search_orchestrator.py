"""SearchOrchestrator 搜索进度失败站点汇总测试"""

import threading
import time
from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.search_context import SearchContext
from app.services.search_orchestrator import SearchOrchestrator


def _make_orchestrator() -> SearchOrchestrator:
    return SearchOrchestrator(
        searcher=MagicMock(),
        search_repo=MagicMock(),
        download_repo=MagicMock(),
        downloader=MagicMock(),
        media_service=MagicMock(),
        message=MagicMock(),
        progress_helper=MagicMock(),
        event_bus=MagicMock(),
        intent_resolver=None,
    )


def _set_progress(orch: SearchOrchestrator, detail: dict) -> None:
    orch._progress.get_process = MagicMock(return_value=detail)


class TestHydrateTimeout:
    def test_slow_hydrate_does_not_block_search(self):
        release = threading.Event()

        class _SlowMetadata:
            def hydrate_media(self, media):
                release.wait(3)

        orch = _make_orchestrator()
        orch._metadata_service = _SlowMetadata()
        started = time.monotonic()
        orch._hydrate_with_timeout(MediaInfo(org_string="SONE-028"), timeout=0.2)
        elapsed = time.monotonic() - started
        release.set()

        assert elapsed < 1.0


class TestFailedSitesSummary:
    def test_no_sites_returns_empty(self):
        orch = _make_orchestrator()
        _set_progress(orch, {"value": 100, "text": "x"})
        assert orch._failed_sites_summary("search:s1") == ""

    def test_no_failed_sites_returns_empty(self):
        orch = _make_orchestrator()
        _set_progress(
            orch,
            {
                "sites": [
                    {"name": "站点A", "status": "ok", "count": 3, "error": ""},
                ]
            },
        )
        assert orch._failed_sites_summary("search:s1") == ""

    def test_mixed_sites_summarizes_failures(self):
        orch = _make_orchestrator()
        _set_progress(
            orch,
            {
                "sites": [
                    {"name": "站点A", "status": "ok", "count": 3, "error": ""},
                    {"name": "站点B", "status": "error", "count": 0, "error": "超时"},
                    {"name": "站点C", "status": "timeout", "count": 0, "error": "超过 10s"},
                ]
            },
        )
        summary = orch._failed_sites_summary("search:s1")
        assert "站点B(超时)" in summary
        assert "站点C(超过 10s)" in summary
        assert "站点A" not in summary

    def test_failed_site_without_error_uses_status(self):
        orch = _make_orchestrator()
        _set_progress(
            orch,
            {
                "sites": [
                    {"name": "站点D", "status": "error", "count": 0, "error": ""},
                ]
            },
        )
        assert "站点D(error)" in orch._failed_sites_summary("search:s1")


class TestOrchestrateFinalText:
    def test_final_text_includes_failed_sites(self):
        """orchestrate 结束时 progress 文本带失败站点汇总"""
        from unittest.mock import MagicMock, patch

        from app.services.search_context import SearchContext

        orch = _make_orchestrator()
        ctx = MagicMock(spec=SearchContext)
        ctx.session_id = "s1"
        ctx.keyword = "测试"
        ctx.no_exists = {}
        ctx.user_name = ""
        ctx.match_media = None
        ctx.persist = False
        ctx.auto_download = False
        ctx.user_id = None
        ctx.ident_flag = True

        orch._searcher.search_one_media = MagicMock(return_value=([MagicMock()], {}, None, None))
        orch._progress = MagicMock()
        orch._progress.get_process.return_value = {
            "sites": [
                {"name": "站点B", "status": "error", "count": 0, "error": "超时"},
            ]
        }
        with (
            patch("app.services.search_orchestrator.SearchResultDeduplicator.deduplicate", return_value=[MagicMock()]),
            patch("app.services.search_orchestrator.SearchResultProcessor.sort_results", side_effect=lambda x, **kw: x),
            patch.object(orch, "_enrich_and_persist"),
            patch.object(orch, "_filter_downloaded", return_value=[]),
        ):
            orch.orchestrate(ctx)

        calls = [str(c) for c in orch._progress.update_max.call_args_list]
        final = [c for c in calls if "搜索完成" in c]
        assert final, "应有搜索完成的 progress update"
        assert "站点B(超时)" in final[-1]


class TestProviderIdentityRecovery:
    def test_wrong_movie_identity_retries_tv_and_keeps_multilingual_search(self):
        orch = _make_orchestrator()
        wrong = MediaInfo(
            title="The Private Navy of Sgt. O'Farrell",
            en_name="The Private Navy of Sgt. O'Farrell",
            original_title="The Private Navy of Sgt. O'Farrell",
            year="1968",
            type=MediaType.MOVIE,
            tmdb_id=106449,
            provider_data={"id": 106449, "title": "The Private Navy of Sgt. O'Farrell"},
        )
        correct = MediaInfo(
            title="凡人修仙传",
            cn_name="凡人修仙传",
            en_name="A Record of a Mortal's Journey to Immortality",
            original_title="A Record of a Mortal's Journey to Immortality",
            original_language="zh",
            year="2020",
            type=MediaType.TV,
            tmdb_id=106449,
            provider_data={"id": 106449, "name": "凡人修仙传", "media_type": "tv"},
        )
        orch._media.get_media_info = cast(Any, MagicMock(side_effect=[wrong, correct]))
        orch._media.get_tmdb_zhtw_title = cast(Any, MagicMock(return_value=None))
        ctx = SearchContext(
            keyword="凡人修仙传",
            session_id="provider-retry",
            search_type=SearchType.WEB,
            filter_args={"site": None},
        )

        names, _, filter_args = orch._prepare_search(ctx)

        assert ctx.match_media is correct
        assert filter_args["type"] == MediaType.TV.value
        assert filter_args["year"] == "2020"
        assert "凡人修仙传" in names
        assert "A Record of a Mortal's Journey to Immortality" in names
        assert all("Private Navy" not in name for name in names)
        assert cast(Any, orch._media.get_media_info).call_count == 2

    def test_invalid_supplied_identity_does_not_leak_type_or_year(self):
        orch = _make_orchestrator()
        wrong = MediaInfo(
            title="The Private Navy of Sgt. O'Farrell",
            en_name="The Private Navy of Sgt. O'Farrell",
            year="1968",
            type=MediaType.MOVIE,
            tmdb_id=106449,
            provider_data={"id": 106449, "title": "The Private Navy of Sgt. O'Farrell"},
        )
        orch._media.get_media_info = cast(Any, MagicMock(return_value=None))
        ctx = SearchContext(
            keyword="凡人修仙传",
            session_id="invalid-provider",
            search_type=SearchType.WEB,
            match_media=wrong,
        )

        names, _, filter_args = orch._prepare_search(ctx)

        assert ctx.match_media is None
        assert names == ["凡人修仙传"]
        assert filter_args["year"] is None
        assert filter_args.get("type") is None


class TestSiteTier:
    def test_default_site_tier_beats_fallback_priority(self):
        default_site = MediaInfo(title="A", type=MediaType.MOVIE)
        default_site.site = "DefaultSite"
        default_site.site_order = 100
        fallback = MediaInfo(title="B", type=MediaType.MOVIE)
        fallback.site = "FallbackSite"
        fallback.site_order = 9999

        result = SearchOrchestrator._apply_site_tier([fallback, default_site], {"site_tier": ["DefaultSite"]})

        assert result[1].site_order > result[0].site_order

    def test_no_tier_keeps_site_order(self):
        media = MediaInfo(title="A", type=MediaType.MOVIE)
        media.site = "Site"
        media.site_order = 10

        result = SearchOrchestrator._apply_site_tier([media], {})

        assert result[0].site_order == 10


class TestContentIdSource:
    def test_resolved_media_keeps_real_provider(self):
        orchestrator = object.__new__(SearchOrchestrator)
        service = MagicMock()
        service.search.return_value = [{"ref": {"provider": "javdb", "external_id": "P0dyv"}}]
        orchestrator._metadata_service = service
        resolved = MediaInfo(title="SSIS-522", type=MediaType.MOVIE)
        orchestrator.resolve_anchor_media = MagicMock(return_value=resolved)

        media = orchestrator.resolve_content_id_media("javalibrary", "SSIS-522", media_type=MediaType.MOVIE)

        assert media is not None
        assert media.provider == "javdb"
        assert media.metadata_ref == "javdb:P0dyv"
        assert media.anchor_provider == "content_id"
        assert media.anchor_external_id == "SSIS-522"


class TestAnchorMediaTitle:
    def test_prefers_original_title_over_numeric_alias(self):
        orchestrator = object.__new__(SearchOrchestrator)
        service = MagicMock()
        service.lookup.return_value = {
            "title": "生化危机：爆发夜",
            "original_title": "Resident Evil",
            "year": "2026",
            "aliases": ["Resident Evil 0", "生化危机0"],
        }
        orchestrator._metadata_service = service

        media = orchestrator.resolve_anchor_media("douban", "37068446", media_type=MediaType.MOVIE)

        assert media is not None
        assert media.title == "生化危机：爆发夜"
        assert media.en_name == "Resident Evil"
        assert media.year == "2026"

    def test_zero_year_is_normalized_to_empty(self):
        orchestrator = object.__new__(SearchOrchestrator)
        service = MagicMock()
        service.lookup.return_value = {"title": "Demo", "original_title": "Demo", "year": "0"}
        orchestrator._metadata_service = service

        media = orchestrator.resolve_anchor_media("douban", "1", media_type=MediaType.MOVIE)

        assert media is not None
        assert media.year == ""


class TestSeasonSuffix:
    def test_anchor_title_parses_season_number(self):
        orchestrator = object.__new__(SearchOrchestrator)
        service = MagicMock()
        service.lookup.return_value = {
            "title": "赛博朋克：边缘行者 第二季",
            "original_title": "Cyberpunk: Edgerunners",
            "year": "2026",
        }
        orchestrator._metadata_service = service

        media = orchestrator.resolve_anchor_media("douban", "1", media_type=MediaType.TV)

        assert media is not None
        assert media.begin_season == 2

    def test_strip_season_suffix_for_search_name(self):
        from app.services.search_service import _strip_season_suffix

        assert _strip_season_suffix("赛博朋克：边缘行者 第二季") == "赛博朋克：边缘行者"
        assert _strip_season_suffix("Cyberpunk Edgerunners Season 2") == "Cyberpunk Edgerunners"
