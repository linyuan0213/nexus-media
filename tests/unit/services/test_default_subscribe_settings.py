"""默认订阅设置的用户维度键与回退测试."""

from app.domain.mediatypes import MediaType
from app.services.subscribe.default_settings import default_setting_key, get_default_setting


class _Config:
    def __init__(self, values: dict):
        self.values = values
        self.keys: list[str] = []

    def get(self, key):
        self.keys.append(str(key))
        return self.values.get(str(key))


class TestDefaultSettingKey:
    def test_movie_global_key(self):
        assert default_setting_key(MediaType.MOVIE) == "DefaultSubscribeSettingMovie"

    def test_movie_profile_key(self):
        assert default_setting_key(MediaType.MOVIE, "adult") == "DefaultSubscribeSettingMovie::adult"

    def test_user_scope_appended(self):
        assert default_setting_key(MediaType.MOVIE, "adult", 7) == "DefaultSubscribeSettingMovie::adult::u7"

    def test_tv_user_scope(self):
        assert default_setting_key(MediaType.TV, None, 7) == "DefaultSubscribeSettingTV::u7"


class TestGetDefaultSetting:
    def test_user_value_wins(self):
        cfg = _Config(
            {
                "DefaultSubscribeSettingMovie::u7": {"rule": 2},
                "DefaultSubscribeSettingMovie": {"rule": 1},
            }
        )

        assert get_default_setting(cfg, MediaType.MOVIE, None, 7) == {"rule": 2}

    def test_missing_user_value_falls_back_to_global(self):
        cfg = _Config({"DefaultSubscribeSettingMovie": {"rule": 1}})

        assert get_default_setting(cfg, MediaType.MOVIE, None, 7) == {"rule": 1}

    def test_no_config_returns_empty(self):
        assert get_default_setting(None, MediaType.MOVIE) == {}
