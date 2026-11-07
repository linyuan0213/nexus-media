"""转移媒体身份补全测试."""

from unittest.mock import MagicMock

from app.db.repositories.identity_resolver import IdentityResolver
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.services.transfer.filetransfer_service import FileTransferService


def test_ensure_identity_resolves_tmdb_reference():
    repo = MagicMock()
    repo.find_by_ref.return_value = type("Identity", (), {"IDENTITY_ID": "01ABC"})()
    svc = object.__new__(FileTransferService)
    svc._identity_resolver = IdentityResolver(repo)
    media = MediaInfo(title="DEMO-001", type=MediaType.ANIME, tmdb_id="220542")

    FileTransferService._ensure_identity(svc, media)

    assert media.identity_id == "01ABC"
    repo.find_by_ref.assert_called_once()


def test_ensure_identity_keeps_existing_identity():
    repo = MagicMock()
    svc = object.__new__(FileTransferService)
    svc._identity_resolver = IdentityResolver(repo)
    media = MediaInfo(title="DEMO-001", type=MediaType.ANIME, identity_id="01KEEP")

    FileTransferService._ensure_identity(svc, media)

    assert media.identity_id == "01KEEP"
    repo.find_by_ref.assert_not_called()
