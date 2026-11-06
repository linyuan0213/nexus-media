"""自定义画像详情链接测试."""

from types import SimpleNamespace

from api.routers.media import _record_detail_data
from app.domain.mediatypes import MediaType
from app.media.metadata import registry as metadata_registry


def test_custom_profile_record_builds_provider_links(monkeypatch):
    monkeypatch.setattr(
        metadata_registry,
        "provider_detail_url",
        lambda provider, external_id, media_type=None: (
            f"https://bgm.tv/subject/{external_id}" if provider == "bangumi" else ""
        ),
    )
    monkeypatch.setattr(
        metadata_registry,
        "get_provider",
        lambda provider: SimpleNamespace(descriptor=SimpleNamespace(display_name="Bangumi")),
    )
    record = {
        "provider": "bangumi",
        "external_id": "511936",
        "title": "罗梅莉亚战记",
        "refs": [
            {"provider": "bangumi", "external_id": "511936"},
            {"provider": "tmdb", "external_id": "999"},
        ],
    }
    data = _record_detail_data(record, MediaType.ANIME, None)
    assert data["links"] == [
        {
            "provider": "bangumi",
            "label": "Bangumi",
            "url": "https://bgm.tv/subject/511936",
        }
    ]
    assert data["link"] == "https://bgm.tv/subject/511936"
    assert data["tmdbid"] == "999"


def test_custom_profile_without_refs_uses_primary_provider(monkeypatch):
    monkeypatch.setattr(
        metadata_registry,
        "provider_detail_url",
        lambda provider, external_id, media_type=None: f"https://example.test/{external_id}",
    )
    monkeypatch.setattr(
        metadata_registry,
        "get_provider",
        lambda provider: SimpleNamespace(descriptor=SimpleNamespace(display_name=provider.upper())),
    )
    data = _record_detail_data(
        {"provider": "bangumi", "external_id": "511936", "title": "测试"},
        MediaType.ANIME,
        None,
    )
    assert data["link"] == "https://example.test/511936"
    assert data["links"][0]["label"] == "BANGUMI"
