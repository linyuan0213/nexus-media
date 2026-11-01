"""MetadataService 单元测试（fake provider，无网络）."""

from typing import Any, Literal

import pytest

from app.core.exceptions import ValidationError
from app.domain.mediatypes import MediaType
from app.media.metadata import (
    ProviderCapability,
    ProviderDescriptor,
    ProviderRecord,
    ProviderRef,
    get_preset,
)
from app.media.metadata.registry import MetadataRegistry
from app.services.metadata_service import MetadataService


class _FakeProvider:
    def __init__(
        self,
        key: str,
        title: str,
        *,
        visibility: Literal["public", "private"] = "public",
        capabilities=None,
        media_type=MediaType.MOVIE,
        media_types=None,
    ):
        self.descriptor = ProviderDescriptor(
            provider_key=key,
            display_name=key,
            capabilities=frozenset(capabilities or {ProviderCapability.DETAIL}),
            media_types=frozenset(media_types or {media_type}),
            visibility=visibility,
        )
        self._title = title

    def detail(self, ref, ctx):
        return ProviderRecord(
            provider=self.descriptor.provider_key,
            external_id=ref.external_id,
            refs=[ProviderRef(provider=self.descriptor.provider_key, external_id=ref.external_id)],
            media_type=MediaType.MOVIE,
            title=self._title,
            overview=f"{self._title} overview",
        )


class _FakeSnapshotRepo:
    def __init__(self):
        self.saved = []
        self.identities = []
        self.refs = []
        self.snapshots = []

    def find_by_ref(self, provider, external_id, *, scope="default", media_type=None) -> Any:
        return None

    def latest_snapshot(self, identity_id, *, policy_key=None, scope=None) -> Any:
        if not self.snapshots:
            return None
        if scope is not None:
            scoped = [item for item in self.snapshots if getattr(item, "SCOPE", "default") == scope]
            return scoped[-1] if scoped else None
        return self.snapshots[-1]

    def get_overrides(self, identity_id, *, user_id=None):
        return []

    def get_identity(self, identity_id) -> Any:
        return None

    def list_refs(self, identity_id):
        return []

    def list_pending_links(self, *, limit=100):
        return []

    def review_link(self, identity_id, **kwargs):
        return None

    def merge_identity(self, source_id, target_id):
        return False

    def ensure_identity(self, **kwargs):
        identity = type("Identity", (), {"IDENTITY_ID": f"id-{len(self.identities) + 1}"})()
        self.identities.append((identity, kwargs))
        return identity

    def upsert_ref(self, identity_id, **kwargs):
        self.refs.append((identity_id, kwargs))
        return kwargs

    def upsert_override(self, identity_id, **kwargs):
        row = type("Override", (), {"as_dict": lambda: {"identity_id": identity_id, **kwargs}})()
        return row

    def set_parent(self, identity_id, parent_identity_id, season_number):
        return True

    def save_snapshot(self, identity_id, **kwargs):
        self.saved.append((identity_id, kwargs))
        self.snapshots.append(
            type(
                "Snapshot",
                (),
                {
                    "CREATED_AT": __import__("datetime").datetime.now(),
                    "SNAPSHOT_HASH": kwargs["snapshot_hash"],
                    "PAYLOAD": __import__("json").dumps(kwargs["payload"]),
                    "SCOPE": kwargs.get("scope", "default"),
                },
            )()
        )


def _service(visibility: Literal["public", "private"] = "public"):
    reg = MetadataRegistry()
    reg.register_provider(_FakeProvider("tmdb", "TMDB 标题", visibility=visibility))
    reg.register_provider(_FakeProvider("douban", "豆瓣标题", visibility=visibility))
    repo = _FakeSnapshotRepo()
    return MetadataService(registry=reg, identity_repo=repo, register_builtins=False), repo


def test_preview_uses_anchor_policy_and_returns_snapshot():
    svc, _ = _service()
    result = svc.preview(
        [
            ProviderRef(provider="tmdb", external_id="1", media_type=MediaType.MOVIE),
            ProviderRef(provider="douban", external_id="2", media_type=MediaType.MOVIE),
        ],
        anchor_provider="douban",
    )

    assert result.metadata is not None
    assert result.metadata.fields["title"].value == "豆瓣标题"
    assert result.degraded is False


def test_preview_rejects_private_provider_without_permission():
    svc, _ = _service(visibility="private")
    with pytest.raises(ValidationError, match="私有来源"):
        svc.preview([ProviderRef(provider="tmdb", external_id="1")], allow_private=False)


def test_preview_allows_private_provider_with_permission():
    svc, _ = _service(visibility="private")
    result = svc.preview([ProviderRef(provider="tmdb", external_id="1")], allow_private=True)
    assert result.metadata is not None


def test_save_snapshot_delegates_to_repository():
    svc, repo = _service()
    result = svc.preview([ProviderRef(provider="tmdb", external_id="1", media_type=MediaType.MOVIE)])
    assert result.metadata is not None

    svc.save_snapshot("identity-1", result.metadata, "tmdb_primary")

    assert repo.saved
    identity_id, kwargs = repo.saved[0]
    assert identity_id == "identity-1"
    assert kwargs["policy_key"] == "tmdb_primary"
    assert kwargs["snapshot_hash"] == result.metadata.snapshot_hash


def test_get_policy_anchor_resolution():
    svc, _ = _service()
    assert svc.get_policy(None, anchor_provider="douban").key == get_preset("douban_primary").key
    assert svc.get_policy("tmdb_primary", anchor_provider="douban").key == "tmdb_primary"


def test_link_subscription_maps_legacy_id_and_writes_ref():
    svc, repo = _service()

    class _MediaInfo:
        tmdb_id = "DB:1292052"
        title = "肖申克的救赎"
        year = "1994"

    fields = svc.link_subscription(_MediaInfo(), media_type=MediaType.MOVIE)

    assert fields.identity_id is not None
    assert fields.anchor_provider == "douban"
    assert fields.anchor_external_id == "1292052"
    assert {(item[1]["provider"], item[1]["external_id"]) for item in repo.refs} == {("douban", "1292052")}
    assert fields.content_profile == "default"
    assert repo.identities
    assert repo.identities[0][1]["media_type"] == "movie"


def test_link_subscription_does_not_block_on_repo_failure():
    class _BrokenRepo:
        def find_by_ref(self, provider, external_id, *, scope="default", media_type=None):
            return None

        def latest_snapshot(self, identity_id, *, policy_key=None, scope=None):
            return None

        def get_overrides(self, identity_id, *, user_id=None):
            return []

        def get_identity(self, identity_id):
            return None

        def list_refs(self, identity_id):
            return []

        def list_pending_links(self, *, limit=100):
            return []

        def review_link(self, identity_id, **kwargs):
            return None

        def merge_identity(self, source_id, target_id):
            return False

        def ensure_identity(self, **kwargs):
            raise RuntimeError("db down")

        def upsert_ref(self, identity_id, **kwargs):
            return kwargs

        def upsert_override(self, identity_id, **kwargs):
            return type("Override", (), {"as_dict": lambda: kwargs})()

        def set_parent(self, identity_id, parent_identity_id, season_number):
            return True

        def save_snapshot(self, identity_id, **kwargs):
            return None

    svc = MetadataService(registry=MetadataRegistry(), identity_repo=_BrokenRepo(), register_builtins=False)

    class _MediaInfo:
        tmdb_id = "278"
        title = "x"
        year = "1994"

    fields = svc.link_subscription(_MediaInfo(), media_type=MediaType.MOVIE)

    assert fields.identity_id is None
    assert fields.anchor_provider == "tmdb"
    assert fields.anchor_external_id == "278"


def test_link_subscription_uses_clicked_mediaid_as_anchor():
    svc, repo = _service()

    class _MediaInfo:
        tmdb_id = "278"
        title = "肖申克的救赎"
        year = "1994"

    fields = svc.link_subscription(_MediaInfo(), media_type=MediaType.MOVIE, mediaid="DB:1292052")

    assert fields.anchor_provider == "douban"
    assert fields.anchor_external_id == "1292052"
    written = {(item[1]["provider"], item[1]["external_id"]) for item in repo.refs}
    assert written == {("douban", "1292052"), ("tmdb", "278")}
    assert fields.metadata_policy == "douban_primary"


def test_resolve_subscription_policy_follows_anchor():
    svc, _ = _service()

    class _Sub:
        metadata_policy = None
        anchor_provider = "douban"

    assert svc.resolve_subscription_policy(_Sub()).key == "douban_primary"

    class _Explicit:
        metadata_policy = "tmdb_primary"
        anchor_provider = "douban"

    assert svc.resolve_subscription_policy(_Explicit()).key == "tmdb_primary"


def test_compose_for_media_uses_douban_ref_without_tmdb():
    svc, _ = _service()

    class _MediaInfo:
        type = MediaType.TV
        tmdb_id = "DB:1"
        douban_id = "1"
        title = "豆瓣剧"
        year = "2024"

    snapshot = svc.compose_for_media(_MediaInfo())

    assert snapshot is not None
    assert snapshot.fields["title"].value == "豆瓣标题"
    assert snapshot.primary_provider == "douban"
    assert any(ref.provider == "douban" for ref in snapshot.refs)


def test_compose_for_media_sets_tv_season_scope():
    seen = []

    class _ScopeProvider(_FakeProvider):
        def detail(self, ref, ctx):
            seen.append(ref.scope)
            return super().detail(ref, ctx)

    registry = MetadataRegistry()
    registry.register_provider(_ScopeProvider("tmdb", "TMDB 标题"))
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    class _MediaInfo:
        type = MediaType.TV
        tmdb_id = "100088"
        douban_id = None
        title = "剧"
        year = "2023"

        def get_season_seq(self):
            return "2"

    snapshot = svc.compose_for_media(_MediaInfo())

    assert snapshot is not None
    assert "season=2" in seen


def test_compose_for_media_with_episodes_expands_provider_episodes():
    from app.media.metadata import EpisodeRecord

    class _EpisodeProvider(_FakeProvider):
        def episodes(self, ref, season, ctx):
            return [EpisodeRecord(season_number=season, episode_number=1, title="第一集")]

    registry = MetadataRegistry()
    registry.register_provider(_EpisodeProvider("tmdb", "标题"))
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    class _MediaInfo:
        type = MediaType.TV
        tmdb_id = "100088"
        douban_id = None
        title = "剧"
        year = "2023"

        def get_season_seq(self):
            return "2"

    snapshot = svc.compose_for_media(_MediaInfo(), with_episodes=True)

    assert snapshot is not None
    assert snapshot.episodes[0].season_number == 2


def test_compose_for_media_applies_locked_overrides():
    from types import SimpleNamespace

    svc, repo = _service()
    repo.find_by_ref = lambda *args, **kwargs: SimpleNamespace(IDENTITY_ID="id-1")
    repo.get_overrides = lambda *args, **kwargs: [
        SimpleNamespace(
            FIELD_NAME="title",
            VALUE="手动标题",
            PROVIDER="manual",
            EXTERNAL_ID="",
            LOCALE=None,
            LOCKED=1,
        )
    ]

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        title = "自动标题"
        year = "1994"

    snapshot = svc.compose_for_media(_MediaInfo())

    assert snapshot is not None
    assert snapshot.fields["title"].value == "手动标题"
    assert snapshot.fields["title"].locked is True


def test_compose_for_media_persists_and_reuses_snapshot():
    from types import SimpleNamespace

    svc, repo = _service()
    repo.find_by_ref = lambda *args, **kwargs: SimpleNamespace(IDENTITY_ID="id-2")

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        title = "自动标题"
        year = "1994"

    first = svc.compose_for_media(_MediaInfo(), persist=True)
    second = svc.compose_for_media(_MediaInfo(), max_age_seconds=3600)

    assert first is not None and second is not None
    assert repo.saved
    assert second.snapshot_hash == first.snapshot_hash


def test_compose_for_media_expands_all_seasons_when_no_season():
    from app.media.metadata import EpisodeRecord, ProviderRecord, SeasonRecord

    class _AllSeasonProvider(_FakeProvider):
        def detail(self, ref, ctx):
            return ProviderRecord(
                provider="tmdb",
                external_id=ref.external_id,
                refs=[ProviderRef(provider="tmdb", external_id=ref.external_id)],
                media_type=MediaType.TV,
                title="全季剧",
                seasons=[SeasonRecord(season_number=1), SeasonRecord(season_number=2)],
            )

        def episodes(self, ref, season, ctx):
            return [EpisodeRecord(season_number=season, episode_number=1, title=f"S{season}E1")]

    registry = MetadataRegistry()
    registry.register_provider(
        _AllSeasonProvider(
            "tmdb",
            "全季剧",
            capabilities={ProviderCapability.DETAIL, ProviderCapability.SEASONS, ProviderCapability.EPISODES},
        )
    )
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    class _MediaInfo:
        type = MediaType.TV
        tmdb_id = "100"
        douban_id = None
        title = "全季剧"
        year = "2023"

        def get_season_seq(self):
            return None

    snapshot = svc.compose_for_media(_MediaInfo(), with_episodes=True)

    assert snapshot is not None
    assert {(item.season_number, item.episode_number) for item in snapshot.episodes} == {(1, 1), (2, 1)}


def test_list_providers_includes_health_and_runtime():
    svc, _ = _service()
    providers = svc.list_providers()

    assert {item["provider"] for item in providers} == {"tmdb", "douban"}
    assert all("health" in item for item in providers)


def test_search_and_lookup_use_registry_providers():
    from app.media.metadata import SearchHit

    class _SearchProvider(_FakeProvider):
        def search(self, query, ctx):
            return [
                SearchHit(
                    provider="tmdb",
                    ref=ProviderRef(provider="tmdb", external_id="1"),
                    title=f"{query.query}-hit",
                    score=9,
                )
            ]

    registry = MetadataRegistry()
    registry.register_provider(
        _SearchProvider("tmdb", "标题", capabilities={ProviderCapability.DETAIL, ProviderCapability.SEARCH})
    )
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    hits = svc.search(query="测试")
    assert hits[0]["title"] == "测试-hit"

    assert svc.lookup("tmdb", "1") is None
    detail = svc.lookup("tmdb", "1", media_type=MediaType.MOVIE)
    assert detail is not None
    assert detail["title"] == "标题"


def test_lookup_cache_isolates_media_type_for_same_external_id():
    class _TypedProvider(_FakeProvider):
        def detail(self, ref, ctx):
            media_type = ref.media_type or MediaType.MOVIE
            return ProviderRecord(
                provider=self.descriptor.provider_key,
                external_id=ref.external_id,
                refs=[ProviderRef(provider=self.descriptor.provider_key, external_id=ref.external_id)],
                media_type=media_type,
                title=f"{media_type.value}:{ref.external_id}",
            )

    registry = MetadataRegistry()
    registry.register_provider(
        _TypedProvider(
            "tmdb",
            "标题",
            media_types={MediaType.MOVIE, MediaType.TV},
        )
    )
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    movie = svc.lookup("tmdb", "106449", media_type=MediaType.MOVIE)
    tv = svc.lookup("tmdb", "106449", media_type=MediaType.TV)

    assert movie is not None and movie["title"] == "movie:106449"
    assert tv is not None and tv["title"] == "tv:106449"


def test_compose_for_media_uses_content_profile_aggregate_provider():
    from app.media.metadata import ProviderRecord

    class _AggregateProvider(_FakeProvider):
        def detail(self, ref, ctx):
            return ProviderRecord(
                provider="adult",
                external_id=ref.external_id,
                refs=[ProviderRef(provider="adult", external_id=ref.external_id, scope="adult")],
                media_type=MediaType.MOVIE,
                content_profile="adult",
                title="聚合标题",
            )

    registry = MetadataRegistry()
    registry.register_provider(_AggregateProvider("adult", "聚合标题"))
    svc = MetadataService(registry=registry, identity_repo=_FakeSnapshotRepo(), register_builtins=False)

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = None
        douban_id = None
        content_profile = "adult"
        anchor_external_id = "ABC-123"
        title = "文件标题"
        year = "2024"

    snapshot = svc.compose_for_media(_MediaInfo())

    assert snapshot is not None
    assert snapshot.fields["title"].value == "聚合标题"
    assert snapshot.content_profile == "adult"


def test_compose_for_media_adds_anchor_ref_for_douban_primary():
    svc, _ = _service()

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        content_profile = "default"
        anchor_provider = "douban"
        anchor_external_id = "2"

        def get_season_seq(self):
            return 0

    snapshot = svc.compose_for_media(_MediaInfo(), with_episodes=False)

    assert snapshot is not None
    assert snapshot.primary_provider == "douban"
    assert snapshot.fields["title"].value == "豆瓣标题"
    assert {(ref.provider, ref.external_id) for ref in snapshot.refs} == {
        ("tmdb", "278"),
        ("douban", "2"),
    }


def test_system_default_policy_uses_explicit_override():
    svc = MetadataService(system_default_policy="douban_primary", register_builtins=False)
    assert svc.system_default_policy == "douban_primary"


def test_system_default_policy_reads_current_settings(monkeypatch):
    from app.core.settings import settings

    monkeypatch.setattr(settings.media, "metadata_default_policy", "bangumi_primary")
    svc = MetadataService(register_builtins=False)
    assert svc.system_default_policy == "bangumi_primary"


def test_identify_anchor_follows_policy(monkeypatch):
    from types import SimpleNamespace

    from app.domain.mediatypes import MediaType

    svc = MetadataService(register_builtins=True)
    svc._ensure_builtin()
    calls = []

    def fake_search(**kwargs):
        calls.append(kwargs["provider"])
        if kwargs["provider"] == "douban":
            return [{"title": "测试电影", "year": "2024", "ref": {"provider": "douban", "external_id": "123"}}]
        return []

    monkeypatch.setattr(svc, "search", fake_search)
    media = SimpleNamespace(title="测试电影", year="2024", type=MediaType.MOVIE, content_profile="default")
    assert svc.identify_anchor(media, policy="douban_primary") is True
    assert media.anchor_provider == "douban"
    assert media.anchor_external_id == "123"
    assert calls == ["douban"]


def test_identify_anchor_falls_back_when_primary_misses(monkeypatch):
    from types import SimpleNamespace

    from app.domain.mediatypes import MediaType

    svc = MetadataService(register_builtins=True)
    svc._ensure_builtin()

    def fake_search(**kwargs):
        if kwargs["provider"] == "bangumi":
            return [{"title": "测试动画", "year": "2024", "ref": {"provider": "bangumi", "external_id": "456"}}]
        return []

    monkeypatch.setattr(svc, "search", fake_search)
    media = SimpleNamespace(title="测试动画", year="2024", type=MediaType.ANIME, content_profile="default")
    assert svc.identify_anchor(media, policy="douban_primary") is True
    assert media.anchor_provider == "bangumi"
    assert media.anchor_external_id == "456"


def test_identify_anchor_singleflight(monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from app.domain.mediatypes import MediaType

    svc = MetadataService(register_builtins=True)
    svc._ensure_builtin()
    call_count = 0
    count_lock = threading.Lock()

    def fake_search(**kwargs):
        nonlocal call_count
        with count_lock:
            call_count += 1
        time.sleep(0.1)
        return [{"title": "并发测试", "year": "2024", "ref": {"provider": "douban", "external_id": "789"}}]

    monkeypatch.setattr(svc, "search", fake_search)
    media_items = [
        SimpleNamespace(title="并发测试", year="2024", type=MediaType.MOVIE, content_profile="default")
        for _ in range(6)
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda item: svc.identify_anchor(item, policy="douban_primary"), media_items))
    assert all(results)
    assert call_count == 1
    assert all(item.anchor_external_id == "789" for item in media_items)


def test_compose_for_media_ignores_cached_empty_snapshot():
    """旧版本落库的空快照（无标题/图片）不能阻止重新合成."""
    from datetime import datetime
    from types import SimpleNamespace

    from app.media.metadata import MediaMetadata

    svc, repo = _service()
    repo.find_by_ref = lambda *args, **kwargs: SimpleNamespace(IDENTITY_ID="id-2")
    empty = MediaMetadata(identity_id="id-2")
    repo.snapshots.append(
        SimpleNamespace(
            CREATED_AT=datetime.now(),
            SNAPSHOT_HASH="empty",
            PAYLOAD=empty.model_dump_json(),
            SCOPE="default",
        )
    )

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        title = "自动标题"
        year = "1994"

    snapshot = svc.compose_for_media(_MediaInfo(), max_age_seconds=3600)

    assert snapshot is not None
    assert snapshot.fields["title"].value
    assert snapshot.snapshot_hash != "empty"


def test_compose_for_media_recomposes_cached_snapshot_missing_images():
    """provider 声明 IMAGES 时，旧快照缺图片应重新合成并落库."""
    from datetime import datetime
    from types import SimpleNamespace

    from app.media.metadata import FieldValue, MediaMetadata

    reg = MetadataRegistry()
    reg.register_provider(
        _FakeProvider(
            "tmdb",
            "TMDB 标题",
            capabilities={ProviderCapability.DETAIL, ProviderCapability.IMAGES},
        )
    )
    repo = _FakeSnapshotRepo()
    svc = MetadataService(registry=reg, identity_repo=repo, register_builtins=False)
    repo.find_by_ref = lambda *args, **kwargs: SimpleNamespace(IDENTITY_ID="id-2")
    cached = MediaMetadata(
        identity_id="id-2",
        fields={"title": FieldValue(value="旧标题", provider="tmdb", external_id="1")},
    )
    repo.snapshots.append(
        SimpleNamespace(
            CREATED_AT=datetime.now(),
            SNAPSHOT_HASH="old",
            PAYLOAD=cached.model_dump_json(),
            SCOPE="default",
        )
    )

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        title = "自动标题"
        year = "1994"

    snapshot = svc.compose_for_media(_MediaInfo(), persist=True, max_age_seconds=3600)

    assert snapshot is not None
    assert snapshot.fields["title"].value == "TMDB 标题"
    assert repo.saved


def test_compose_for_media_recomposes_cached_snapshot_missing_poster():
    """只有 fanart 没有 poster 的快照仍不完整，转移阶段不能直接复用."""
    from datetime import datetime
    from types import SimpleNamespace

    from app.media.metadata import FieldValue, ImageAsset, MediaMetadata

    reg = MetadataRegistry()
    reg.register_provider(
        _FakeProvider(
            "tmdb",
            "TMDB 标题",
            capabilities={ProviderCapability.DETAIL, ProviderCapability.IMAGES},
        )
    )
    repo = _FakeSnapshotRepo()
    svc = MetadataService(registry=reg, identity_repo=repo, register_builtins=False)
    repo.find_by_ref = lambda *args, **kwargs: SimpleNamespace(IDENTITY_ID="id-2")
    cached = MediaMetadata(
        identity_id="id-2",
        fields={"title": FieldValue(value="旧标题", provider="tmdb", external_id="1")},
        images={"fanart": [ImageAsset(type="fanart", url="https://example.com/f.jpg")]},
    )
    repo.snapshots.append(
        SimpleNamespace(
            CREATED_AT=datetime.now(),
            SNAPSHOT_HASH="old",
            PAYLOAD=cached.model_dump_json(),
            SCOPE="default",
        )
    )

    class _MediaInfo:
        type = MediaType.MOVIE
        tmdb_id = "278"
        douban_id = None
        title = "自动标题"
        year = "1994"

    snapshot = svc.compose_for_media(_MediaInfo(), persist=True, max_age_seconds=3600)

    assert snapshot is not None
    assert snapshot.fields["title"].value == "TMDB 标题"
    assert repo.saved
