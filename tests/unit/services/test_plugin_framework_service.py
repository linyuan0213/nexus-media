"""PluginFrameworkService 单元测试."""

import json
import zipfile
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import PluginError
from app.services.plugin_framework_service import PluginFrameworkService


def _make_manifest_json(version: str) -> dict:
    return {"id": "demo", "name": "Demo", "version": version}


def _make_zip(path, version: str = "1.1.0") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(_make_manifest_json(version)))
        zf.writestr("backend/plugin.py", "NEW")


def _make_old_orm(old_dir, version: str = "1.0.0") -> SimpleNamespace:
    return SimpleNamespace(
        ID="demo",
        NAME="Demo",
        VERSION=version,
        AUTHOR="",
        DESCRIPTION="",
        CATEGORY="tool",
        TAGS="[]",
        ICON="",
        COLOR="",
        MANIFEST_JSON=json.dumps(_make_manifest_json(version)),
        ENABLED=True,
        INSTALLED=True,
        INSTALLED_AT=None,
        UPDATED_AT=None,
        PATH=str(old_dir),
    )


class TestPluginInstallRollback:
    def _service(self, tmp_path, old_orm, *, update_ok: bool):
        repo = MagicMock()
        repo.get_manifest_by_id.return_value = old_orm
        repo.update_manifest.return_value = update_ok
        repo.insert_manifest.return_value = True
        registry = MagicMock()
        state = MagicMock()
        state.enabled = True
        state.installed = True
        registry.get_state.return_value = state
        sandbox = MagicMock()
        sandbox.load.return_value = True
        svc = PluginFrameworkService(
            repo=repo,
            menu_repo=MagicMock(),
            role_repo=MagicMock(),
            plugin_registry=registry,
            plugin_sandbox=sandbox,
            hook_system=MagicMock(),
        )
        svc._plugins_dir = str(tmp_path)
        return svc

    def _run_install(self, svc, zip_path):
        with patch("app.services.plugin_framework_service.get_lock_manager") as glm:
            lock = MagicMock()
            lock.acquire.return_value = True
            glm.return_value.create_lock.return_value = lock
            return svc._do_install(str(zip_path))

    def test_update_failure_restores_old_dir_and_manifest(self, tmp_path):
        old_dir = tmp_path / "demo-1.0.0"
        (old_dir / "backend").mkdir(parents=True)
        (old_dir / "backend" / "plugin.py").write_text("OLD", encoding="utf-8")
        old_orm = _make_old_orm(old_dir)
        svc = self._service(tmp_path, old_orm, update_ok=False)
        zip_path = tmp_path / "new.zip"
        _make_zip(zip_path, "1.1.0")

        with pytest.raises(PluginError):
            self._run_install(svc, zip_path)

        assert (old_dir / "backend" / "plugin.py").read_text(encoding="utf-8") == "OLD"
        assert not (tmp_path / "demo-1.1.0").exists()
        restored = cast(MagicMock, svc._repo).update_manifest.call_args_list[-1].args[0]
        assert restored.path == str(old_dir)
        assert restored.enabled is True
        cast(MagicMock, svc._plugin_sandbox).load.assert_called_with("demo")

    def test_same_version_reinstall_failure_restores_backup(self, tmp_path):
        old_dir = tmp_path / "demo-1.0.0"
        (old_dir / "backend").mkdir(parents=True)
        (old_dir / "backend" / "plugin.py").write_text("OLD", encoding="utf-8")
        old_orm = _make_old_orm(old_dir, "1.0.0")
        svc = self._service(tmp_path, old_orm, update_ok=False)
        zip_path = tmp_path / "same.zip"
        _make_zip(zip_path, "1.0.0")

        with pytest.raises(PluginError):
            self._run_install(svc, zip_path)

        assert (old_dir / "backend" / "plugin.py").read_text(encoding="utf-8") == "OLD"
        assert not list(tmp_path.glob("demo-1.0.0.bak-*"))


class TestPluginLifecycleGuard:
    def _service(self):
        svc = PluginFrameworkService(
            repo=MagicMock(),
            menu_repo=MagicMock(),
            role_repo=MagicMock(),
            plugin_registry=MagicMock(),
            plugin_sandbox=MagicMock(),
        )
        return svc

    def test_guard_is_reentrant_within_same_thread(self):
        svc = self._service()
        with patch("app.services.plugin_framework_service.get_lock_manager") as glm:
            lock = MagicMock()
            lock.acquire.return_value = True
            glm.return_value.create_lock.return_value = lock

            with svc._lifecycle_guard("demo"):
                with svc._lifecycle_guard("demo"):
                    pass

        glm.return_value.create_lock.assert_called_once_with("plugin:lifecycle:demo", ttl_seconds=300)
        lock.release.assert_called_once()

    def test_guard_rejects_when_lock_not_acquired(self):
        svc = self._service()
        with patch("app.services.plugin_framework_service.get_lock_manager") as glm:
            lock = MagicMock()
            lock.acquire.return_value = False
            glm.return_value.create_lock.return_value = lock

            with pytest.raises(PluginError):
                with svc._lifecycle_guard("demo"):
                    pass


class TestPluginFrameworkServiceGetPluginPath:
    def _service(self, orm_path: str | None = None, registry_path: str | None = None):
        repo = MagicMock()
        orm_model = MagicMock()
        orm_model.PATH = orm_path
        repo.get_manifest_by_id.return_value = orm_model if orm_path is not None else None
        registry = MagicMock()
        registry.get_plugin_path.return_value = registry_path
        return PluginFrameworkService(
            repo=repo,
            menu_repo=MagicMock(),
            role_repo=MagicMock(),
            plugin_registry=registry,
            plugin_sandbox=MagicMock(),
        )

    def test_get_plugin_path_prefers_existing_db_path(self):
        svc = self._service(orm_path="/db/plugins/foo-1.0.0", registry_path="/registry/plugins/foo-1.0.0")
        with patch("app.services.plugin_framework_service.os.path.exists", return_value=True):
            path = svc.get_plugin_path("foo")
        assert path == "/db/plugins/foo-1.0.0"

    def test_get_plugin_path_fallback_when_db_path_missing(self):
        svc = self._service(orm_path="/db/plugins/foo-1.0.0", registry_path="/registry/plugins/foo-1.0.0")
        with patch("app.services.plugin_framework_service.os.path.exists", return_value=False):
            path = svc.get_plugin_path("foo")
        assert path == "/registry/plugins/foo-1.0.0"
        cast(MagicMock, svc._plugin_registry).get_plugin_path.assert_called_once_with("foo")

    def test_get_plugin_path_fallback_when_no_db_record(self):
        svc = self._service(orm_path=None, registry_path="/registry/plugins/foo-1.0.0")
        with patch("app.services.plugin_framework_service.os.path.exists", return_value=False):
            path = svc.get_plugin_path("foo")
        assert path == "/registry/plugins/foo-1.0.0"

    def test_get_plugin_path_returns_none_when_no_path_found(self):
        svc = self._service(orm_path="/db/plugins/foo-1.0.0", registry_path=None)
        with patch("app.services.plugin_framework_service.os.path.exists", return_value=False):
            path = svc.get_plugin_path("foo")
        assert path is None


class TestPluginFrameworkContentProfileDefaults:
    def test_overlay_defaults_without_mutating_manifest(self):
        profiles = [
            {
                "key": "custom",
                "default_search_source": "source_a",
                "default_detail_source": "detail_a",
                "search_sources": [
                    {"label": "Source A", "value": "source_a"},
                    {"label": "Source B", "value": "source_b"},
                ],
            }
        ]
        config = {
            "content_profile_defaults": {
                "custom": {
                    "default_search_source": "source_b",
                    "default_detail_source": "detail_b",
                }
            }
        }
        merged = PluginFrameworkService._apply_content_profile_defaults(profiles, config)
        assert merged[0]["default_search_source"] == "source_b"
        assert merged[0]["default_detail_source"] == "detail_b"
        assert profiles[0]["default_search_source"] == "source_a"

    def test_overlay_ignores_unknown_search_source(self):
        profiles = [
            {
                "key": "custom",
                "default_search_source": "source_a",
                "search_sources": [{"label": "Source A", "value": "source_a"}],
            }
        ]
        config = {"content_profile_defaults": {"custom": {"default_search_source": "unknown"}}}
        merged = PluginFrameworkService._apply_content_profile_defaults(profiles, config)
        assert merged[0]["default_search_source"] == "source_a"
