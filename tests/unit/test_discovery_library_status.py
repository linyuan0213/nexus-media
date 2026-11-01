from typing import Any, cast
from unittest.mock import MagicMock

from app.domain.mediatypes import MediaType
from app.media.metadata.models import DiscoveryItem
from app.plugin_sdk.metadata import ProviderRef
from app.services.library_presence_service import LibraryPresenceService


def _item(code: str, *, title: str | None = None) -> DiscoveryItem:
    return DiscoveryItem(
        provider="demo",
        ref=ProviderRef(provider="demo", external_id=f"slug-{code}", media_type=MediaType.MOVIE),
        anchor_ref=ProviderRef(provider="content_id", external_id=code, media_type=MediaType.MOVIE),
        content_profile="custom",
        title=title or code,
    )


def _service(*, transfer=None, sync=None, live=None, background=False, identity=None, identity_ids=None):
    transfer_repo = MagicMock()
    transfer_repo.get_existing_anchors.return_value = transfer or set()
    transfer_repo.get_existing_identity_ids.return_value = identity_ids or set()
    sync_repo = MagicMock()
    sync_repo.get_existing_anchors.return_value = sync or set()
    sync_repo.get_existing_identity_ids.return_value = set()
    media_server = MagicMock()
    media_server.check_library_present_any.side_effect = live or (lambda *a, **k: False)
    identity_repo = MagicMock()
    identity_repo.find_by_ref.return_value = identity
    service = LibraryPresenceService(
        transfer_repo=transfer_repo,
        media_sync_repo=sync_repo,
        media_server=media_server,
        identity_repo=identity_repo,
        warm_in_background=background,
    )
    service._identity_repo = identity_repo
    service._transfer_repo = transfer_repo
    service._media_sync_repo = sync_repo
    return service


def test_transfer_success_wins_over_missing_media_library():
    items = [_item("ABC-123"), _item("ABC-124")]
    service = _service(transfer={("content_id", "ABC-123")})

    service.annotate(items)

    assert items[0].extra["in_library"] is True
    assert "in_library" not in items[1].extra


def test_media_library_sync_used_when_transfer_history_missing():
    items = [_item("ABC-200")]
    service = _service(sync={("content_id", "ABC-200")})

    service.annotate(items)

    assert items[0].extra["in_library"] is True


def test_live_multi_instance_check_is_last_resort():
    items = [_item("ABC-300")]
    service = _service(live=lambda *a, **k: True)

    service.annotate(items)

    assert items[0].extra["in_library"] is True
    cast(MagicMock, service._media_server).check_library_present_any.assert_called_once()


def test_sync_lookup_is_batched():
    items = [_item("ABC-400"), _item("ABC-401")]
    service = _service()

    service.annotate(items)

    cast(MagicMock, service._media_sync_repo).get_existing_anchors.assert_called_once()


def test_live_result_is_cached_and_prewarmed():
    items = [_item("ABC-500")]
    service = _service(live=lambda *a, **k: True, background=False)
    service.warm(items)

    service.annotate(items)

    assert items[0].extra["in_library"] is True
    cast(MagicMock, service._media_server).check_library_present_any.assert_called_once()


def test_content_id_anchor_resolves_through_identity_graph():
    items = [_item("ABC-449")]
    identity = MagicMock()
    identity.IDENTITY_ID = "identity-1"
    service = _service(identity=identity, identity_ids={"identity-1"})

    service.annotate(items)

    assert items[0].extra["in_library"] is True
    cast(Any, service._identity_repo).find_by_ref.assert_called()
    cast(Any, service._transfer_repo).get_existing_identity_ids.assert_called_with(["identity-1"])

