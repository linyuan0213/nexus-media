"""MetadataComposer 单元测试."""

from app.domain.mediatypes import MediaType
from app.media.metadata import (
    Credit,
    EpisodeRecord,
    FieldValue,
    ImageAsset,
    MediaMetadata,
    MetadataComposer,
    ProviderCapability,
    ProviderRecord,
    ProviderRef,
    SeasonRecord,
    get_preset,
    resolve_policy,
)


def _record(provider: str, **overrides) -> ProviderRecord:
    data = {
        "provider": provider,
        "external_id": f"{provider}-1",
        "refs": [ProviderRef(provider=provider, external_id=f"{provider}-1")],
        "media_type": MediaType.TV,
        "content_profile": "default",
    }
    data.update(overrides)
    return ProviderRecord(**data)


def _douban_record() -> ProviderRecord:
    return _record(
        "douban",
        locale="zh-CN",
        title="最后生还者 第一季",
        original_title="The Last of Us Season 1",
        year="2023",
        overview="中文简介",
        genres=["剧情", "科幻"],
        ratings={"douban": 9.0},
        images={"poster": [ImageAsset(type="poster", url="douban-poster")]},
        credits=[Credit(name="佩德罗·帕斯卡")],
        extra={"honor": "Top250"},
    )


def _tmdb_record() -> ProviderRecord:
    return _record(
        "tmdb",
        locale="zh-CN",
        title="最后生还者",
        original_title="The Last of Us",
        year="2023",
        release_date="2023-01-15",
        runtime=44,
        overview="TMDB 中文简介",
        genres=["剧情", "动作"],
        ratings={"tmdb": 8.6},
        images={
            "poster": [ImageAsset(type="poster", url="tmdb-poster")],
            "backdrop": [ImageAsset(type="backdrop", url="tmdb-backdrop")],
            "logo": [ImageAsset(type="logo", url="tmdb-logo")],
        },
        credits=[Credit(name="Pedro Pascal"), Credit(name="Bella Ramsey")],
        seasons=[SeasonRecord(season_number=1, episode_count=9)],
        episodes=[
            EpisodeRecord(season_number=1, episode_number=1, title="迷失在黑暗之中", runtime=81),
            EpisodeRecord(season_number=1, episode_number=2, title="感染者", runtime=53),
        ],
        extra={"popularity": 100},
    )


def test_tmdb_primary_prefers_tmdb_and_keeps_ratings_namespaced():
    snapshot = MetadataComposer().compose("id-1", [_douban_record(), _tmdb_record()], get_preset("tmdb_primary"))

    assert snapshot.fields["title"].value == "最后生还者"
    assert snapshot.fields["title"].provider == "tmdb"
    assert snapshot.ratings == {"tmdb": 8.6, "douban": 9.0}
    assert snapshot.fields["release_date"].value == "2023-01-15"
    assert snapshot.fields["runtime"].provider == "tmdb"
    assert set(snapshot.genres) == {"剧情", "动作", "科幻"}


def test_tmdb_primary_still_prefers_tmdb_when_tmdb_has_no_locale():
    tmdb = _tmdb_record()
    tmdb.locale = None
    snapshot = MetadataComposer().compose("id-1", [_douban_record(), tmdb], get_preset("tmdb_primary"))

    assert snapshot.fields["title"].value == "最后生还者"
    assert snapshot.fields["title"].provider == "tmdb"


def test_douban_primary_uses_douban_text_and_tmdb_structure():
    snapshot = MetadataComposer().compose("id-1", [_tmdb_record(), _douban_record()], get_preset("douban_primary"))

    assert snapshot.fields["title"].value == "最后生还者 第一季"
    assert snapshot.fields["title"].provider == "douban"
    assert snapshot.fields["overview"].value == "中文简介"
    assert snapshot.fields["release_date"].provider == "tmdb"
    assert snapshot.fields["runtime"].provider == "tmdb"
    assert snapshot.images["poster"][0].url == "douban-poster"
    assert snapshot.images["backdrop"][0].url == "tmdb-backdrop"
    assert [episode.episode_number for episode in snapshot.episodes] == [1, 2]
    assert [season.season_number for season in snapshot.seasons] == [1]
    assert snapshot.ratings == {"douban": 9.0, "tmdb": 8.6}


def test_douban_only_partial_snapshot_has_no_structure():
    snapshot = MetadataComposer().compose("id-1", [_douban_record()], get_preset("douban_primary"))

    assert snapshot.fields["title"].value == "最后生还者 第一季"
    assert snapshot.seasons == []
    assert snapshot.episodes == []
    assert "backdrop" not in snapshot.images


def test_capabilities_filter_excludes_unsupported_fields():
    capabilities = {
        "douban": {ProviderCapability.DETAIL},
        "tmdb": {ProviderCapability.DETAIL, ProviderCapability.IMAGES},
    }
    snapshot = MetadataComposer().compose(
        "id-1",
        [_douban_record(), _tmdb_record()],
        get_preset("douban_primary"),
        capabilities=capabilities,
    )

    # douban 未声明 IMAGES 能力，海报回退 TMDB
    assert snapshot.seasons == []
    assert snapshot.episodes == []
    assert snapshot.images["poster"][0].url == "tmdb-poster"


def test_locked_field_wins_over_policy():
    locked = {
        "title": FieldValue(value="手动标题", provider="manual", external_id="manual", locked=True),
    }
    snapshot = MetadataComposer().compose(
        "id-1",
        [_douban_record(), _tmdb_record()],
        get_preset("tmdb_primary"),
        locked=locked,
    )

    assert snapshot.fields["title"].value == "手动标题"
    assert snapshot.fields["title"].locked is True


def test_extra_namespaced_and_conflicts_recorded():
    record = _tmdb_record()
    record.year = "2024"
    snapshot = MetadataComposer().compose("id-1", [_douban_record(), record], get_preset("douban_primary"))

    assert snapshot.extra["douban.honor"] == "Top250"
    assert snapshot.extra["tmdb.popularity"] == 100
    conflicts = {item["field"] for item in snapshot.extra["conflicts"]}
    assert "year" in conflicts
    # 「最后生还者 第一季」与「最后生还者」是包含关系，不算标题冲突
    assert "title" not in conflicts


def test_snapshot_hash_stable_across_record_order():
    composer = MetadataComposer()
    first = composer.compose("id-1", [_douban_record(), _tmdb_record()], get_preset("douban_primary"))
    second = composer.compose("id-1", [_tmdb_record(), _douban_record()], get_preset("douban_primary"))

    assert first.snapshot_hash == second.snapshot_hash
    assert len(first.snapshot_hash) == 64


def test_refs_include_all_providers():
    snapshot = MetadataComposer().compose("id-1", [_douban_record(), _tmdb_record()], get_preset("tmdb_primary"))
    providers = {(ref.provider, ref.external_id) for ref in snapshot.refs}
    assert ("douban", "douban-1") in providers
    assert ("tmdb", "tmdb-1") in providers


def test_resolve_policy_priority():
    assert resolve_policy("tmdb_primary", anchor_provider="douban").key == "tmdb_primary"
    assert resolve_policy(None, anchor_provider="douban").key == "douban_primary"
    assert resolve_policy(None, anchor_provider="bangumi").key == "bangumi_primary"
    assert resolve_policy(None).key == "tmdb_primary"
    assert resolve_policy("provider_only:custom").primary == "custom"


def test_media_type_resolved_from_records():
    snapshot = MetadataComposer().compose("id-1", [_douban_record()], get_preset("douban_primary"))
    assert snapshot.media_type == MediaType.TV
    assert isinstance(snapshot, MediaMetadata)


def test_douban_primary_prefers_all_douban_fields_when_available():
    douban = _douban_record().model_copy(
        update={
            "release_date": "2023-01-15",
            "runtime": 45,
            "images": {
                "poster": [ImageAsset(type="poster", url="douban-poster")],
                "backdrop": [ImageAsset(type="backdrop", url="douban-backdrop")],
            },
        }
    )
    snapshot = MetadataComposer().compose("id-1", [douban, _tmdb_record()], get_preset("douban_primary"))
    assert snapshot.images["poster"][0].url == "douban-poster"
    assert snapshot.images["backdrop"][0].url == "douban-backdrop"
    assert snapshot.fields["release_date"].provider == "douban"
    assert snapshot.fields["runtime"].provider == "douban"


def test_provider_only_keeps_fused_images_and_credits():
    """provider_only 聚合记录应完整保留标题/海报/演员，不因字段过滤丢失."""
    fused = _record(
        "demo",
        title="PRWF-017 示例标题",
        overview="简介",
        images={
            "poster": [ImageAsset(type="poster", url="https://img/poster.jpg")],
            "fanart": [ImageAsset(type="fanart", url="https://img/fanart.jpg")],
        },
        credits=[Credit(name="小松空", role="actor")],
        extra={"source_provider": "dmm"},
    )
    snapshot = MetadataComposer().compose(
        "id-1",
        [fused],
        get_preset("provider_only:demo"),
        content_profile="demo",
        capabilities={
            "demo": {
                ProviderCapability.DETAIL,
                ProviderCapability.IMAGES,
                ProviderCapability.CREDITS,
            }
        },
    )

    assert snapshot.fields["title"].value == "PRWF-017 示例标题"
    assert snapshot.primary_provider == "demo"
    assert snapshot.images["poster"][0].url == "https://img/poster.jpg"
    assert snapshot.images["fanart"][0].url == "https://img/fanart.jpg"
    assert snapshot.credits[0].name == "小松空"
