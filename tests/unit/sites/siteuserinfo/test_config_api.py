"""ConfigApiUserInfo 用户信息解析单元测试."""

from app.sites.userinfo.providers.config_api import ConfigApiUserInfo


class TestConfigApiUserInfo:
    def test_resolve_json_path_timestamp_to_date(self):
        data = {"data": {"regTime": 1714478855}}
        field_cfg = {
            "source": "data.regTime",
            "transform": "timestamp_to_date",
        }
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == "2024-04-30 20:07:35"

    def test_resolve_json_path_timestamp_to_date_string(self):
        data = {"data": {"regTime": "1714478855"}}
        field_cfg = {
            "source": "data.regTime",
            "transform": "timestamp_to_date",
        }
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == "2024-04-30 20:07:35"

    def test_resolve_json_path_map_value(self):
        data = {"data": {"status": 1}}
        field_cfg = {
            "source": "data.status",
            "transform": "map_value",
            "map": {"1": "active", "0": "inactive"},
        }
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == "active"

    def test_resolve_json_path_no_transform(self):
        data = {"data": {"regTime": 1714478855}}
        field_cfg = {
            "source": "data.regTime",
        }
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == 1714478855

    def test_resolve_json_path_size(self):
        data = {"data": {"user": {"stats": {"uploaded": "1.5 GB"}}}}
        field_cfg = {"source": "data.user.stats.uploaded", "type": "size"}
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == int(1.5 * 1024**3)

    def test_resolve_json_path_size_zero(self):
        data = {"data": {"user": {"stats": {"downloaded": "0 B"}}}}
        field_cfg = {"source": "data.user.stats.downloaded", "type": "size"}
        result = ConfigApiUserInfo._resolve_json_path(data, field_cfg)
        assert result == 0


class TestConfigApiSeeding:
    def test_seeding_uses_params_and_accumulates_size(self, monkeypatch):
        info = object.__new__(ConfigApiUserInfo)
        info.site_name = "猪猪"
        info.userid = 25775  # type: ignore[assignment]
        info.seeding = 0
        info.seeding_size = 0
        info.seeding_info = "[]"
        calls = []

        def fake_api_call(endpoint_cfg, body=None, params=None):
            calls.append((body, params))
            return {"data": {"items": [{"seeders": 2, "size": 1024}], "pages": 1}}

        monkeypatch.setattr(info, "_api_call", fake_api_call)
        info._parse_seeding(
            {
                "seeding": {
                    "method": "POST",
                    "path": "/v1/api/me/torrents",
                    "params": {"kind": "seeding", "page": "{page}", "per_page": 100},
                    "body": {},
                    "pagination": {"type": "page_param", "total_pages_key": "data.pages"},
                    "response": {
                        "items_key": "data.items",
                        "seeders_field": "seeders",
                        "size_field": "size",
                    },
                }
            }
        )
        assert calls[0][1] == {"kind": "seeding", "page": "1", "per_page": 100}
        assert info.seeding == 1
        assert info.seeding_size == 1024
