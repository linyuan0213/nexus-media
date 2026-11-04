"""身份统一性不变量测试（CI）."""

import pytest

from app.db.engine import get_engine
from app.db.models import Base
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.services.identity_resolver import IdentityResolver


@pytest.fixture(autouse=True)
def _clean_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_anchor_resolution_never_creates_shadow_identity():
    resolved = IdentityResolver().resolve_values(
        provider="tmdb", external_id="100001", title="Integrity Demo", year="2026"
    )

    assert resolved.identity_id
    assert not resolved.identity_id.startswith(("local:", "content_id:"))
    repo = MediaIdentityRepository()
    assert repo.find_by_ref("tmdb", "100001", media_type="movie") is not None


def test_same_work_resolves_to_one_identity_across_refs_and_title():
    resolver = IdentityResolver()
    first = resolver.resolve_values(provider="tmdb", external_id="100002", title="Same Work", year="2026")
    second = resolver.resolve_values(
        identity_id="content_id:100002",
        title="same work",
        year="2026",
        media_type="movie",
    )

    assert first.identity_id == second.identity_id
    assert MediaIdentityRepository().find_by_ref("tmdb", "100002", media_type="movie") is not None


def test_search_resolution_does_not_fallback_to_local_identity():
    resolved = IdentityResolver().resolve_values(title="Unknown No Anchor", media_type="movie", allow_local=False)

    assert resolved.identity_id == ""


def test_preview_identity_is_resolved_to_real_identity():
    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="movie", title="MIDA-853", year="2026")
    repo.upsert_ref(identity.IDENTITY_ID, provider="content_id", external_id="MIDA-853", media_type="movie")

    resolved = IdentityResolver().resolve_values(
        identity_id="preview",
        title="MIDA-853",
        year="2026",
        media_type="movie",
    )

    assert resolved.identity_id == identity.IDENTITY_ID


def test_cross_provider_external_code_resolves_to_one_identity():
    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="movie", title="MIDA-853 Full Title", year="")
    repo.upsert_ref(identity.IDENTITY_ID, provider="demo_meta", external_id="MIDA-853", media_type="movie")

    resolved = IdentityResolver().resolve_values(
        provider="content_id",
        external_id="MIDA-853",
        title="MIDA-853",
        media_type="movie",
    )

    assert resolved.identity_id == identity.IDENTITY_ID
    assert repo.find_by_ref("content_id", "MIDA-853", media_type="movie") is not None


def test_anonymous_record_does_not_create_local_identity():
    resolved = IdentityResolver().resolve_values(title="", media_type="movie", allow_local=True)
    assert resolved.identity_id == ""
