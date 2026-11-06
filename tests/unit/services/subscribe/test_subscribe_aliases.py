"""订阅别名附加测试."""

from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.services.subscribe.management.query_service import SubscribeQueryService


def test_attach_aliases_by_identity(monkeypatch):
    monkeypatch.setattr(
        MediaIdentityRepository,
        "get_aliases_map",
        staticmethod(lambda ids: {identity_id: ["别名A", "Alias B"] for identity_id in ids}),
    )
    items = {
        "1": {"identity_id": "id-1"},
        "2": {"identity_id": "id-2"},
        "3": {"identity_id": None},
    }
    result = SubscribeQueryService._attach_aliases(items)
    assert result["1"]["aliases"] == ["别名A", "Alias B"]
    assert result["2"]["aliases"] == ["别名A", "Alias B"]
    assert result["3"]["aliases"] == []
