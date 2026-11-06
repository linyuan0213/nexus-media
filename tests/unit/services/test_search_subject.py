"""搜索主体类型/身份矩阵."""

import pytest

from app.domain.mediatypes import MediaType
from app.services.search_subject import SearchSubject


@pytest.mark.parametrize(
    ("media_type", "profile", "provider", "external", "display", "provider_type", "mode"),
    [
        ("movie", "default", "tmdb", "550", MediaType.MOVIE, MediaType.MOVIE, "title"),
        ("tv", "default", "bangumi", "400602", MediaType.TV, MediaType.TV, "title"),
        ("anime", "anime", "tmdb", "283938", MediaType.ANIME, MediaType.TV, "title"),
        (None, "anime", "tmdb", "283938", MediaType.ANIME, MediaType.TV, "title"),
        ("movie", "demo", "content_id", "DEMO-660", MediaType.MOVIE, MediaType.MOVIE, "code"),
        ("movie", "movie", "tmdb", "550", MediaType.MOVIE, MediaType.MOVIE, "title"),
        ("movie", "demo", "demo_provider", "DEMO-969", MediaType.MOVIE, MediaType.MOVIE, "code"),
        (None, "demo", "content_id", "DEMO-969", None, None, "code"),
    ],
)
def test_search_subject_matrix(media_type, profile, provider, external, display, provider_type, mode):
    subject = SearchSubject.classify(media_type, profile, provider, external)
    assert subject.display_type == display
    assert subject.provider_type == provider_type
    assert subject.search_mode == mode
