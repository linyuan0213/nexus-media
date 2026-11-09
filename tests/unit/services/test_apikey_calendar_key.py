"""日历系统 API Key 归属测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.apikey_service import APIKeyService


def test_calendar_system_key_binds_missing_owner():
    svc = APIKeyService.__new__(APIKeyService)
    svc._key_repo = MagicMock()
    svc._key_repo.get_by_name.return_value = SimpleNamespace(id=2, raw_key="nk_calendar", created_by=None)

    assert svc.get_or_create_system_key("CalendarSubscription", created_by=1) == "nk_calendar"
    svc._key_repo.update_key.assert_called_once_with(2, created_by=1)
