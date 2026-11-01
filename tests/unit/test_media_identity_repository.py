"""MediaIdentityRepository 单元测试."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.session import SessionManager


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    manager = SessionManager()
    manager._engine = engine
    manager._factory = sessionmaker(bind=engine, expire_on_commit=False)
    MediaIdentityRepository._session_manager = manager
    yield MediaIdentityRepository()
    engine.dispose()


def test_identity_idempotent_and_lookup_by_ref(repo):
    identity = repo.ensure_identity(media_type="movie", content_profile="default", title="肖申克的救赎", year="1994")
    assert len(identity.IDENTITY_ID) == 26

    again = repo.ensure_identity(identity_id=identity.IDENTITY_ID, title="肖申克的救赎")
    assert again.IDENTITY_ID == identity.IDENTITY_ID

    repo.upsert_ref(identity.IDENTITY_ID, provider="tmdb", external_id="278", media_type="movie")
    found = repo.find_by_ref("tmdb", "278")
    assert found is not None
    assert found.IDENTITY_ID == identity.IDENTITY_ID

    refs = repo.list_refs(identity.IDENTITY_ID)
    assert [(ref.PROVIDER, ref.EXTERNAL_ID) for ref in refs] == [("tmdb", "278")]


def test_tmdb_same_external_id_isolated_by_media_type(repo):
    movie = repo.ensure_identity(media_type="movie")
    tv = repo.ensure_identity(media_type="tv")
    repo.upsert_ref(movie.IDENTITY_ID, provider="tmdb", external_id="106449", media_type="movie")
    repo.upsert_ref(tv.IDENTITY_ID, provider="tmdb", external_id="106449", media_type="tv")

    assert repo.find_by_ref("tmdb", "106449", media_type="movie").IDENTITY_ID == movie.IDENTITY_ID
    assert repo.find_by_ref("tmdb", "106449", media_type="tv").IDENTITY_ID == tv.IDENTITY_ID


def test_ref_cannot_be_reassigned_to_another_identity(repo):
    first = repo.ensure_identity()
    second = repo.ensure_identity()
    repo.upsert_ref(first.IDENTITY_ID, provider="douban", external_id="1292052")

    with pytest.raises(ValueError, match="已属于其他身份"):
        repo.upsert_ref(second.IDENTITY_ID, provider="douban", external_id="1292052")


def test_snapshot_saved_and_latest(repo):
    identity = repo.ensure_identity()
    repo.save_snapshot(
        identity.IDENTITY_ID,
        policy_key="douban_primary",
        content_profile="default",
        snapshot_hash="a" * 64,
        payload={"fields": {"title": "x"}},
        providers=["douban", "tmdb"],
    )
    latest = repo.latest_snapshot(identity.IDENTITY_ID)
    assert latest is not None
    assert latest.POLICY_KEY == "douban_primary"
    assert latest.SNAPSHOT_HASH == "a" * 64
    assert "douban" in (latest.PROVIDERS or "")


def test_override_upsert_updates_value(repo):
    identity = repo.ensure_identity()
    repo.upsert_override(identity.IDENTITY_ID, field_name="title", value="手动标题")
    repo.upsert_override(identity.IDENTITY_ID, field_name="title", value="新标题")

    overrides = repo.get_overrides(identity.IDENTITY_ID)
    assert len(overrides) == 1
    assert overrides[0].VALUE == "新标题"
    assert overrides[0].LOCKED == 1


def test_pending_link_review(repo):
    identity = repo.ensure_identity()
    repo.upsert_ref(identity.IDENTITY_ID, provider="tmdb", external_id="1", reviewed=False)

    pending = repo.list_pending_links()
    assert len(pending) == 1

    reviewed = repo.review_link(
        identity.IDENTITY_ID,
        provider="tmdb",
        external_id="1",
        approve=True,
        confidence=0.9,
    )
    assert reviewed is not None
    assert reviewed.REVIEWED == 1
    assert repo.list_pending_links() == []

    repo.upsert_ref(identity.IDENTITY_ID, provider="douban", external_id="2", reviewed=False)
    assert repo.review_link(identity.IDENTITY_ID, provider="douban", external_id="2", approve=False) is None
    assert repo.find_by_ref("douban", "2") is None


def test_merge_identity_moves_refs(repo):
    source = repo.ensure_identity()
    target = repo.ensure_identity()
    repo.upsert_ref(source.IDENTITY_ID, provider="tmdb", external_id="10")
    repo.upsert_ref(target.IDENTITY_ID, provider="douban", external_id="20")

    assert repo.merge_identity(source.IDENTITY_ID, target.IDENTITY_ID) is True
    assert repo.get_identity(source.IDENTITY_ID) is None
    assert {ref.PROVIDER for ref in repo.list_refs(target.IDENTITY_ID)} == {"tmdb", "douban"}


def test_snapshot_scope_isolated(repo):
    identity = repo.ensure_identity()
    for scope, hash_value in (("season=1", "a" * 64), ("season=8", "b" * 64)):
        repo.save_snapshot(
            identity.IDENTITY_ID,
            policy_key="douban_primary",
            content_profile="default",
            scope=scope,
            snapshot_hash=hash_value,
            payload={"scope": scope},
        )
    latest = repo.latest_snapshot(identity.IDENTITY_ID, scope="season=1")
    assert latest is not None
    assert latest.SCOPE == "season=1"
    assert latest.SNAPSHOT_HASH == "a" * 64
