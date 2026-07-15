"""ConfigApiUserInfo 用户信息解析单元测试."""

from app.sites.siteuserinfo.config_api import ConfigApiUserInfo


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
