"""统一身份解析服务测试."""

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


def test_anchor_resolution_creates_and_reuses_identity():
    resolver = IdentityResolver()
    first = resolver.resolve_values(provider="tmdb", external_id="12345", title="Demo", year="2026")
    second = resolver.resolve_values(provider="tmdb", external_id="12345", title="Demo", year="2026")

    assert first.identity_id
    assert first.identity_id == second.identity_id
    assert first.provider == "tmdb"


def test_shadow_content_id_resolves_to_canonical():
    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="movie", title="JJDA-001", year="")
    repo.upsert_ref(identity.IDENTITY_ID, provider="content_id", external_id="JJDA-001", media_type="movie")

    resolved = IdentityResolver().resolve_values(
        identity_id="content_id:JJDA-001",
        title="JJDA-001",
        media_type="movie",
    )

    assert resolved.identity_id == identity.IDENTITY_ID


def test_title_matches_anime_family():
    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="tv", title="Anime Demo", year="2026")

    resolved = IdentityResolver().resolve_values(title="Anime Demo", year="2026", media_type="anime")

    assert resolved.identity_id == identity.IDENTITY_ID


def test_search_resolution_does_not_create_local_identity():
    resolved = IdentityResolver().resolve_values(title="Unknown Title", media_type="movie", allow_local=False)

    assert resolved.identity_id == ""


def test_tracked_resolution_allows_local_fallback():
    resolved = IdentityResolver().resolve_values(title="Unknown Title", media_type="movie", allow_local=True)

    assert resolved.identity_id.startswith("local:")
