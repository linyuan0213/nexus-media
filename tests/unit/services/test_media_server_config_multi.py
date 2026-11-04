"""同类型媒体服务器多实例配置测试。"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.media  # noqa: F401  # 先完成 app.media 初始化，避免既有 SystemConfig 循环导入
from app.services.system.config import MediaServerConfigService


class _Repo:
    def __init__(self):
        self.rows = []
        self.next_id = 1

    def get_media_servers(self, sid=None):
        return [row for row in self.rows if sid is None or row.ID == sid]

    def get_media_server_by_name(self, name):
        return next((row for row in self.rows if row.NAME == name), None)

    def get_default_media_server(self):
        return next((row for row in self.rows if row.IS_DEFAULT), None)

    def update_media_server(self, sid, name, enabled, config, is_default=0, note=None, server_type=None):
        if sid is None:
            sid = self.next_id
            self.next_id += 1
            self.rows.append(
                SimpleNamespace(
                    ID=sid, NAME=name, TYPE=server_type, CONFIG=config, ENABLED=enabled, IS_DEFAULT=is_default
                )
            )
        else:
            row = self.get_media_servers(sid)[0]
            row.NAME = name
            row.TYPE = server_type
            row.CONFIG = config
            row.ENABLED = enabled
            row.IS_DEFAULT = is_default

    def set_default_media_server_id(self, sid):
        for row in self.rows:
            row.IS_DEFAULT = int(row.ID == sid)

    def delete_media_server(self, sid):
        self.rows = [row for row in self.rows if row.ID != sid]


def test_save_two_same_type_instances():
    repo = _Repo()
    service = MediaServerConfigService(MagicMock(), config_repo=repo)

    assert service.save_config({"name": "普通 Emby", "type": "emby", "enabled": 1, "is_default": 1}).success
    assert service.save_config({"name": "演示 Emby", "type": "emby", "enabled": 1}).success

    info = service.get_media_servers_info()["servers"]
    assert len(info) == 2
    assert info["普通 Emby"]["type"] == "emby"
    assert info["演示 Emby"]["type"] == "emby"
    assert info["普通 Emby"]["id"] != info["演示 Emby"]["id"]


def test_legacy_type_update_reuses_existing_instance():
    repo = _Repo()
    service = MediaServerConfigService(MagicMock(), config_repo=repo)
    service.save_config({"name": "emby", "type": "emby", "enabled": 1, "host": "old"})
    assert repo.get_default_media_server() is not None

    result = service.save_config({"type": "emby", "host": "new"})

    assert result.success
    assert len(repo.rows) == 1
    assert json.loads(repo.rows[0].CONFIG)["host"] == "new"


def test_apply_config_targets_alias_instance():
    repo = _Repo()
    service = MediaServerConfigService(MagicMock(), config_repo=repo)
    service.save_config({"name": "普通 Emby", "type": "emby", "enabled": 1, "host": "normal"})
    service.save_config({"name": "演示 Emby", "type": "emby", "enabled": 1, "host": "demo"})

    service.apply_config("演示 Emby", {"host": "demo-new"})

    servers = service.get_media_servers_info()["servers"]
    assert servers["演示 Emby"]["config"]["host"] == "demo-new"
    assert servers["普通 Emby"]["config"]["host"] == "normal"


def test_default_and_delete_guards():
    repo = _Repo()
    service = MediaServerConfigService(MagicMock(), config_repo=repo)
    service.save_config({"name": "普通 Emby", "type": "emby", "enabled": 1, "is_default": 1})
    service.save_config({"name": "演示 Emby", "type": "emby", "enabled": 1})

    assert not service.delete_config(1).success
    assert service.set_default(2).success
    default = repo.get_default_media_server()
    assert default is not None and default.ID == 2
    assert service.delete_config(1).success
    assert len(repo.rows) == 1
    assert service.delete_config(2).success
    assert repo.rows == []
