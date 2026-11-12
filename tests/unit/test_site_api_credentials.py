"""站点 API 凭据加密与实体字段测试."""

from app.domain.entities.site import SiteEntity
from app.utils.credential_crypto import decrypt_secret, encrypt_secret


def test_credential_secret_roundtrip():
    raw = '{"bearer_token":"jwt-value","visitor_id":"abc"}'
    encrypted = encrypt_secret(raw)
    assert encrypted
    assert encrypted != raw
    assert decrypt_secret(encrypted) == raw


def test_empty_secret_is_empty():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""
    assert decrypt_secret("not-a-fernet-token") == ""


def test_site_entity_has_api_credentials_field():
    entity = SiteEntity(api_credentials={"spa": {"bearer_token": "token"}})
    assert entity.to_dict()["api_credentials"]["spa"]["bearer_token"] == "token"
