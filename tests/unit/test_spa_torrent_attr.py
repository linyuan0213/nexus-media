"""SPA torrent_attr 端到端属性解析测试（HTTP 层 mock）."""

import json
from unittest.mock import patch

from app.sites.engine import SiteEngine


def test_spa_torrent_attr_maps_free_and_labels():
    engine = SiteEngine(definitions_dir="config/sites")
    payload = {
        "code": 0,
        "data": {
            "item": {
                "id": 57233,
                "promotion": {"down": 0, "up": 1, "label": "免费"},
                "hr": False,
                "seeders": 14,
                "tags": [{"name": "国语"}, {"name": "中字"}],
            }
        },
    }
    user_note = {"api_credentials": {"spa": {"bearer_token": "jwt", "visitor_id": "v"}}}
    with (
        patch("app.sites.engine.HttpClient") as client_cls,
        patch("app.sites.engine.engine_tools.spa_signed_headers", return_value={}),
    ):
        client_cls.return_value.get.return_value.text = json.dumps(payload)
        result = engine.resolve_torrent_attr("https://piggo.me/detail/57233", note=user_note)
    assert result["free"] is True
    assert result["peer_count"] == 14
    assert result["labels"] == "国语,中字,免费"
