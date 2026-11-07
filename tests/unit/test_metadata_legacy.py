from app.domain.media_types import ProviderMediaType
from app.media.metadata.legacy import parse_legacy_ref


def test_content_id_prefix_is_not_claimed_by_real_provider():
    ref = parse_legacy_ref("content_id:SSNI-865", ProviderMediaType.MOVIE)

    assert ref is not None
    assert ref.provider == "content_id"
    assert ref.external_id == "SSNI-865"
