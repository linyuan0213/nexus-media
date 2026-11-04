"""WEB 资源搜索应继承默认订阅过滤规则."""

from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.services.search_web_entry import _apply_default_rule, _apply_default_sites, make_web_search_fn


def test_apply_default_sites_includes_default_filter_rule():
    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": 10000}
    args: dict = {}

    _apply_default_sites(args, None, config, None)

    assert args["rule"] == 10000
    assert args["site"] is None


def test_apply_default_rule_when_sites_are_already_all():
    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": 10000}
    args = {"site": None}

    _apply_default_rule(args, None, config, None)

    assert args["rule"] == 10000


def test_manual_search_ignores_default_rule():
    captured = {}

    class _Orchestrator:
        def orchestrate(self, ctx):
            captured["filter_args"] = ctx.filter_args
            return [], [], 1, []

    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": 10000}
    fn = make_web_search_fn(cast(Any, _Orchestrator()), config)

    fn("凡人修仙传", filters={"site": []}, media_type=MediaType.TV)

    assert captured["filter_args"]["rule"] == -1


def test_custom_profile_web_search_skips_tmdb_identification():
    captured = {}

    class _Orchestrator:
        def orchestrate(self, ctx):
            captured["ident_flag"] = ctx.ident_flag
            captured["filter_args"] = ctx.filter_args
            return [], [], 1, []

    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": 10000}
    fn = make_web_search_fn(cast(Any, _Orchestrator()), config)

    fn("ACHJ-097", filters={"site": [], "content_profile": "adult"}, media_type=None)

    assert captured["ident_flag"] is False
    assert captured["filter_args"]["rule"] == -1


def test_default_sites_and_page_selection_are_merged():
    config = MagicMock()
    config.get.return_value = {"search_sites": ["M-Team"], "rule": ""}
    args: dict = {}

    _apply_default_sites(args, MediaType.TV, config, None, ["观众"])

    assert args["site"] == ["M-Team", "观众"]


def test_page_selection_used_when_default_sites_empty():
    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": ""}
    args: dict = {}

    _apply_default_sites(args, MediaType.MOVIE, config, None, ["观众"])

    assert args["site"] == ["观众"]


def test_all_sites_used_when_default_and_selection_empty():
    config = MagicMock()
    config.get.return_value = {"search_sites": [], "rule": ""}
    args: dict = {}

    _apply_default_sites(args, MediaType.MOVIE, config, None, None)

    assert args["site"] is None
