"""Sukebei 与 M-Team demo 模式配置回归."""

from __future__ import annotations

import json
from pathlib import Path


def test_sukebei_mirrors_nyaa_layout():
    nyaa = json.loads(Path("config/sites/html/nyaa.json").read_text(encoding="utf-8"))
    sukebei = json.loads(Path("config/sites/html/sukebei.json").read_text(encoding="utf-8"))
    assert sukebei["domain"] == "https://sukebei.nyaa.si"
    assert sukebei["html"]["torrents"] == nyaa["html"]["torrents"]
    assert sukebei["html"]["search"] == nyaa["html"]["search"]


def test_mteam_uses_generic_mode_fallback():
    config = json.loads(Path("config/sites/api/mteam.json").read_text(encoding="utf-8"))
    assert "DEMO" not in config["api"]["endpoints"]["search"].get("mode_mapping", {})


def test_profile_search_mode_falls_back_to_lowercase():
    from types import SimpleNamespace

    from app.sites.search.api_searcher import ApiSiteSearcher

    site = SimpleNamespace(
        name="mteam",
        api=SimpleNamespace(
            base_url="https://api.m-team.cc",
            endpoints={
                "search": {
                    "method": "POST",
                    "path": "/api/torrent/search",
                    "body": {"mode": "normal", "keyword": "{keyword}"},
                    "mode_mapping": {"MOVIE": "movie"},
                }
            },
        ),
    )
    from app.media.metadata import ProviderDescriptor
    from app.media.metadata.registry import registry

    class _DemoProvider:
        descriptor = ProviderDescriptor(
            provider_key="test_demo",
            display_name="Demo",
            content_profiles=frozenset({"demo"}),
            search_mode="DEMO",
        )

    registry.register_provider(_DemoProvider(), plugin_id="test")
    try:
        searcher = object.__new__(ApiSiteSearcher)
        setattr(searcher, "_site", site)
        searcher._auth_tokens = {}
        captured = {}
        searcher._execute_request = lambda *args, **kwargs: captured.update(args[1]) or []
        searcher.search(keyword="DEMO-001", content_profile="demo")
        assert captured["mode"] == "demo"
    finally:
        registry.unregister_provider("test_demo", plugin_id="test")

    captured.clear()
    searcher.search(keyword="SSIS-001", content_profile="default")
    assert captured["mode"] == "normal"

    captured.clear()
    searcher.search(keyword="SSIS-001", content_profile="documentary")
    assert captured["mode"] == "normal"
