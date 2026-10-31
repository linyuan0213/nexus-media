"""
Plugin Framework Service
插件框架 v2 业务服务层
"""

import contextlib
import os
import shutil
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

import log
from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    PluginError,
    PluginInstallingError,
    PluginManifestInvalidError,
    PluginNotInstalledError,
)
from app.core.settings import settings
from app.db.repositories.plugin_framework_repository import PluginFrameworkRepository
from app.db.repositories.rbac_repo_adapter import RBACMenuRepositoryAdapter, RBACRoleRepositoryAdapter
from app.domain.entities.plugin import PluginConfigEntity, PluginManifestEntity
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.plugin_framework.private_pack import file_sha256, safe_extract, validate_private_manifest
from app.plugin_framework.registry import PluginRegistry
from app.plugin_framework.sandbox import PluginSandbox
from app.schemas.plugin import PluginManifest
from app.utils.json_utils import JsonUtils


class PluginFrameworkService:
    """插件框架业务服务"""

    def __init__(
        self,
        repo: PluginFrameworkRepository,
        menu_repo: RBACMenuRepositoryAdapter,
        role_repo: RBACRoleRepositoryAdapter,
        plugin_registry: PluginRegistry,
        plugin_sandbox: PluginSandbox,
        hook_system=None,
    ):
        self._repo = repo
        self._menu_repo = menu_repo
        self._role_repo = role_repo
        self._plugin_registry = plugin_registry
        self._plugin_sandbox = plugin_sandbox
        self._hook_system = hook_system
        self._plugins_dir = os.path.join(settings.data_path, "plugins")
        if not os.path.exists(self._plugins_dir):
            os.makedirs(self._plugins_dir)

    def _get_hook_system(self):
        if self._hook_system is None:
            raise RuntimeError("插件钩子系统尚未初始化")
        return self._hook_system

    def _get_plugin_parent_menu(self):
        """获取 Plugin 父菜单"""
        return self._menu_repo.get_menu_by_code("Plugin")

    def _sync_plugin_menus(self, plugin_id: str) -> None:
        """为插件 frontend routes 同步 RBAC 菜单（支持挂到宿主已有菜单下）."""
        manifest = self.get_manifest(plugin_id)
        if not manifest or not manifest.frontend or not manifest.frontend.routes:
            return

        routes = manifest.frontend.routes
        plugin_parent = None
        if any(not r.parent for r in routes):
            plugin_parent = self._ensure_plugin_parent(manifest)
            if not plugin_parent:
                log.warn("[PluginFrameworkService] Plugin 父菜单不存在，跳过默认插件菜单同步")
            else:
                # 新插件父菜单刚创建时尚未分配给任何角色；先挂到拥有“插件中心”的角色，
                # 否则后续子菜单授权找不到父菜单，侧边栏就不会出现插件菜单组。
                self._assign_new_plugin_parent_to_roles(plugin_parent)

        assignments: dict[int, tuple[object, list[int]]] = {}
        for idx, route in enumerate(routes):
            if not route.menu:
                continue

            if route.parent:
                parent = self._menu_repo.get_menu_by_code(route.parent)
                if not parent:
                    log.warn(f"[PluginFrameworkService] 菜单父级不存在: {route.parent}")
                    continue
                if not route.path.startswith("/"):
                    log.warn(f"[PluginFrameworkService] 指定 parent 的插件路由必须使用绝对 path: {route.path}")
                    continue
                full_path = route.path
                permission_code = route.permission or parent.permission_code or "plugin:view"
                menu_level = (parent.menu_level or 1) + 1
            else:
                if not plugin_parent:
                    continue
                parent = plugin_parent
                full_path = route.path if route.path.startswith("/") else f"/plugin/{plugin_id}/{route.path}"
                permission_code = route.permission or "plugin:view"
                menu_level = 3

            safe_path = route.path.strip("/").replace("/", "_") or "index"
            menu_code = f"Plugin_{plugin_id}_{safe_path}"
            existing = self._menu_repo.get_menu_by_code(menu_code)
            sort_order = route.order if route.order is not None else 100 + idx
            if existing:
                child_updates: dict = {
                    "status": 1,
                    "parent_id": parent.id,
                    "menu_level": menu_level,
                    "component": "/plugin/host/index",
                }
                if existing.path != full_path:
                    child_updates["path"] = full_path
                self._menu_repo.update_menu(existing.id, **child_updates)
                menu = existing
            else:
                result = self._menu_repo.create_menu(
                    menu_name=route.title or manifest.name,
                    menu_code=menu_code,
                    parent_id=parent.id,
                    path=full_path,
                    icon=route.icon or "lucide:puzzle",
                    component="/plugin/host/index",
                    sort_order=sort_order,
                    menu_level=menu_level,
                    permission_code=permission_code,
                    hide_in_menu=0,
                )
                menu = result if hasattr(result, "id") else self._menu_repo.get_menu_by_code(menu_code)
                if menu:
                    log.info(f"[PluginFrameworkService] 创建插件菜单: {menu_code} -> {full_path}")
            if not menu:
                continue
            entries = assignments.setdefault(parent.id, (parent, []))
            entries[1].append(menu.id)

        expected_codes = {
            f"Plugin_{plugin_id}_{r.path.strip('/').replace('/', '_') or 'index'}" for r in routes if r.menu
        }
        for menu in self._menu_repo.get_all_menus():
            code = str(getattr(menu, "menu_code", "") or "")
            if code.startswith(f"Plugin_{plugin_id}_") and code not in expected_codes:
                self._menu_repo.delete_menu(menu.id)
                log.info(f"[PluginFrameworkService] 清理过期插件菜单: {code}")

        if not any(not r.parent for r in routes):
            orphan = self._menu_repo.get_menu_by_code(f"Plugin_{plugin_id}")
            if orphan:
                self._menu_repo.delete_menu(orphan.id)

        for parent, menu_ids in assignments.values():
            self._assign_menus_to_authorized_roles(menu_ids, parent)

    def _ensure_plugin_parent(self, manifest):
        """确保插件父菜单存在."""
        root_parent = self._get_plugin_parent_menu()
        if not root_parent:
            return None
        plugin_parent_code = f"Plugin_{manifest.id}"
        plugin_parent = self._menu_repo.get_menu_by_code(plugin_parent_code)
        if not plugin_parent:
            result = self._menu_repo.create_menu(
                menu_name=manifest.name,
                menu_code=plugin_parent_code,
                parent_id=root_parent.id,
                path=f"/plugin/{manifest.id}",
                icon=manifest.icon or "lucide:puzzle",
                component="",
                sort_order=100,
                menu_level=2,
                permission_code="plugin:view",
                hide_in_menu=0,
            )
            return result if hasattr(result, "id") else self._menu_repo.get_menu_by_code(plugin_parent_code)
        parent_updates: dict = {"status": 1}
        if plugin_parent.path != f"/plugin/{manifest.id}":
            parent_updates["path"] = f"/plugin/{manifest.id}"
        self._menu_repo.update_menu(plugin_parent.id, **parent_updates)
        return plugin_parent

    def _remove_plugin_menus(self, plugin_id: str) -> None:
        """删除插件创建的所有菜单（含挂到宿主菜单下的路由）."""
        prefix = f"Plugin_{plugin_id}"
        removed = 0
        for menu in self._menu_repo.get_all_menus():
            code = str(getattr(menu, "menu_code", "") or "")
            if code == prefix or code.startswith(f"{prefix}_"):
                self._menu_repo.delete_menu(menu.id)
                removed += 1
        if removed:
            log.info(f"[PluginFrameworkService] 共删除 {removed} 个插件菜单")

    def _assign_new_plugin_parent_to_roles(self, plugin_parent) -> None:
        """把新建的插件父菜单分配给已拥有根“插件中心”菜单的角色."""
        root_menu = self._get_plugin_parent_menu()
        if not root_menu:
            return
        assigned = 0
        for role in self._role_repo.get_all_roles(status=1):
            if not role.menus:
                continue
            has_root = any(m.get("menu_code") == root_menu.menu_code or m.get("id") == root_menu.id for m in role.menus)
            if not has_root:
                continue
            current_ids = {int(mid) for m in role.menus if (mid := m.get("id")) is not None}
            if plugin_parent.id in current_ids:
                continue
            current_ids.add(plugin_parent.id)
            self._role_repo.assign_menus_to_role(role.id, list(current_ids))
            assigned += 1
        if assigned:
            log.info(f"[PluginFrameworkService] 为 {assigned} 个角色分配插件父菜单: {plugin_parent.menu_code}")

    def _assign_menus_to_authorized_roles(self, menu_ids: list[int], parent_menu=None) -> None:
        """将菜单分配给已拥有父菜单权限的角色."""
        if not menu_ids:
            return
        parent_menu = parent_menu or self._get_plugin_parent_menu()
        if not parent_menu:
            return

        roles = self._role_repo.get_all_roles(status=1)
        for role in roles:
            if not role.menus:
                continue
            has_parent = any(
                m.get("menu_code") == parent_menu.menu_code or m.get("id") == parent_menu.id for m in role.menus
            )
            if not has_parent:
                continue
            current_ids = {int(mid) for m in role.menus if (mid := m.get("id")) is not None}
            current_ids.update(menu_ids)
            self._role_repo.assign_menus_to_role(role.id, list(current_ids))
            log.info(f"[PluginFrameworkService] 为角色 '{role.role_name}' 分配 {len(menu_ids)} 个插件菜单")

    @staticmethod
    def _apply_content_profile_defaults(profiles: list[dict], config: dict) -> list[dict]:
        """把插件配置里的内容画像默认值覆盖到 manifest 声明."""
        overrides = config.get("content_profile_defaults")
        if not isinstance(overrides, dict):
            return profiles
        merged = deepcopy(profiles)
        for profile in merged:
            key = str(profile.get("key") or "")
            override = overrides.get(key)
            if not key or not isinstance(override, dict):
                continue
            sources = {
                str(item.get("value"))
                for item in (profile.get("search_sources") or [])
                if isinstance(item, dict) and item.get("value")
            }
            for field in ("default_search_source", "default_detail_source"):
                value = str(override.get(field) or "").strip()
                if not value:
                    continue
                if field == "default_search_source" and sources and value not in sources:
                    continue
                profile[field] = value
        return merged

    @staticmethod
    def _resolve_installed(orm_model) -> bool:
        """判定插件是否已安装：DB 标记为真，或（非内置且安装目录存在）。

        兼容历史数据中 INSTALLED 缺失/过期（已落盘但标记为 0）的情况，
        避免"市场显示已安装、已安装列表为空"。
        """
        path = str(getattr(orm_model, "PATH", "") or "")
        if bool(getattr(orm_model, "INSTALLED", True)):
            return True
        if path and "builtin_plugins" not in path and os.path.isdir(path):
            return True
        return False

    def list_plugins(self) -> list[dict]:
        """列出所有已安装插件"""
        # 先扫描内置插件（热新增）

        self._plugin_registry.scan_async()
        orm_list = self._repo.get_all_manifests()
        plugins = []
        for orm_model in orm_list:
            try:
                manifest = PluginManifest.from_dict(JsonUtils.loads(str(orm_model.MANIFEST_JSON or "{}")))
                profiles = self._apply_content_profile_defaults(
                    manifest.frontend.content_profiles,
                    self.get_config(manifest.id),
                )
                plugins.append(
                    {
                        "id": manifest.id,
                        "name": manifest.name,
                        "version": manifest.version,
                        "author": manifest.author,
                        "description": manifest.description,
                        "category": manifest.category,
                        "tags": manifest.tags,
                        "icon": manifest.icon,
                        "color": manifest.color,
                        "enabled": bool(orm_model.ENABLED),
                        "is_builtin": bool(orm_model.PATH and "builtin_plugins" in orm_model.PATH),
                        "installed": self._resolve_installed(orm_model),
                        "supports_run": manifest.backend.supports_run,
                        "has_config": bool(
                            manifest.frontend and manifest.frontend.settings and manifest.frontend.settings.fields
                        ),
                        "backend": {
                            "entry": manifest.backend.entry,
                            "api_prefix": manifest.backend.api_prefix,
                            "hooks": manifest.backend.hooks,
                            "supports_run": manifest.backend.supports_run,
                        },
                        "frontend": {
                            "routes": [
                                {
                                    "path": r.path,
                                    "component": r.component,
                                    "title": r.title,
                                    "icon": r.icon,
                                    "menu": r.menu,
                                    "parent": r.parent,
                                    "permission": r.permission,
                                    "order": r.order,
                                }
                                for r in manifest.frontend.routes
                            ],
                            "slots": [
                                {"target": s.target, "position": s.position, "component": s.component}
                                for s in manifest.frontend.slots
                            ],
                            "content_profiles": profiles,
                        },
                    }
                )
            except Exception as e:
                log.error(f"[PluginFrameworkService] 解析插件清单失败: {e}")
        return plugins

    def list_enabled_agent_tools(self) -> list[dict]:
        """已启用插件声明的 Agent 工具（供 ToolExecutor 动态合并，作为能力清单）"""
        tools: list[dict] = []
        try:
            orm_list = self._repo.get_all_manifests()
        except Exception as e:  # noqa: BLE001
            log.warn(f"[PluginFrameworkService]读取插件清单失败，插件工具不可用: {e}")
            return tools
        for orm_model in orm_list:
            if not bool(getattr(orm_model, "ENABLED", False)):
                continue
            try:
                manifest = PluginManifest.from_dict(JsonUtils.loads(str(orm_model.MANIFEST_JSON or "{}")))
            except Exception:  # noqa: BLE001
                continue
            for t in manifest.backend.tools:
                if not t.name:
                    continue
                tools.append(
                    {
                        "plugin_id": manifest.id,
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters or {},
                        "level": t.level,
                        "permission": t.permission,
                    }
                )
        return tools

    def call_agent_tool(self, plugin_id: str, name: str, arguments: dict):
        """调用插件 backend.agent_tool(name, arguments)

        插件返回约定为 {success: bool, data: …, error: str}（data 缺省视为成功数据），
        由 ToolExecutor 统一转换为 ToolResult。
        """
        return self._plugin_sandbox.call(plugin_id, "agent_tool", name, arguments)

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """获取插件完整 manifest"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            return None
        return PluginManifest.from_dict(JsonUtils.loads(str(orm_model.MANIFEST_JSON or "{}")))

    def get_config(self, plugin_id: str) -> dict:
        """获取插件配置"""
        orm_model = self._repo.get_config(plugin_id)
        if orm_model and str(orm_model.CONFIG or ""):
            try:
                return JsonUtils.loads(str(orm_model.CONFIG))
            except Exception as e:  # noqa: BLE001
                log.debug(f"[PluginFrameworkService]忽略异常: {e}")
        return {}

    def get_config_fields(self, plugin_id: str) -> list[dict]:
        """获取插件配置字段定义"""
        manifest = self.get_manifest(plugin_id)
        fields = []
        if manifest and manifest.frontend and manifest.frontend.settings:
            for f in manifest.frontend.settings.fields:
                fields.append(
                    {
                        "key": f.key,
                        "type": f.type,
                        "label": f.label,
                        "default": f.default,
                        "placeholder": f.placeholder,
                        "options": f.options,
                        "source": f.source,
                        "multiple": f.multiple,
                        "required": f.required,
                        "help": f.help,
                    }
                )
        return fields

    def save_config(self, plugin_id: str, config: dict) -> None:
        """保存插件配置；插件重载不阻塞保存接口."""
        entity = PluginConfigEntity(plugin_id=plugin_id, config=config)
        self._repo.save_config(entity)
        self._get_hook_system().emit("plugin.config_changed", {"plugin_id": plugin_id, "config": config})

    def install(self, zip_path: str, expected_sha256: str | None = None) -> PluginManifest:
        """安装插件包（多实例部署时通过分布式锁保证只有一个实例执行安装）"""
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"插件包不存在: {zip_path}")
        if expected_sha256 and file_sha256(zip_path).lower() != expected_sha256.lower():
            raise PluginManifestInvalidError("插件包 SHA-256 校验失败")

        lock_key = f"plugin:install:{os.path.basename(zip_path)}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            log.info(f"[Plugin]插件安装正在进行中，跳过: {zip_path}")
            raise PluginInstallingError("插件安装正在执行中，请稍后再试")

        try:
            return self._do_install(zip_path)
        finally:
            lock.release()

    def _do_install(self, zip_path: str) -> PluginManifest:
        """实际安装逻辑"""
        extract_dir = os.path.join(self._plugins_dir, "__tmp_install")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir)

        safe_extract(zip_path, extract_dir)

        manifest_path = os.path.join(extract_dir, "manifest.json")
        # zip 命令压缩文件夹后，解压出来的根目录是一个子文件夹（如 hello_world/）
        if not os.path.exists(manifest_path):
            for entry in os.listdir(extract_dir):
                subdir = os.path.join(extract_dir, entry)
                if os.path.isdir(subdir):
                    candidate = os.path.join(subdir, "manifest.json")
                    if os.path.exists(candidate):
                        manifest_path = candidate
                        break

        if not os.path.exists(manifest_path):
            shutil.rmtree(extract_dir)
            raise PluginManifestInvalidError("插件包缺少 manifest.json")

        with open(manifest_path, encoding="utf-8") as f:
            manifest_data = JsonUtils.load(f)

        manifest = PluginManifest.from_dict(manifest_data)
        if manifest.backend.metadata.visibility == "private":
            validate_private_manifest(manifest)
        if not manifest.id or not manifest.name:
            shutil.rmtree(extract_dir)
            raise PluginManifestInvalidError("manifest.json 缺少 id 或 name")

        # manifest 所在的真实目录（处理 macOS 压缩的子文件夹情况）
        plugin_root = os.path.dirname(manifest_path)
        target_dir = os.path.join(self._plugins_dir, f"{manifest.id}-{manifest.version}")

        existing = self._repo.get_manifest_by_id(manifest.id)
        was_enabled = bool(existing.ENABLED) if existing else False
        new_manifest_json = JsonUtils.dumps(manifest.to_dict(), ensure_ascii=False)
        # 同版本重装也覆盖文件：仅比较 manifest 会忽略同版本内的代码修复
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(target_dir)
        # 将插件内容移到目标目录
        for item in os.listdir(plugin_root):
            shutil.move(os.path.join(plugin_root, item), target_dir)
        # 清理临时目录
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

        # 检查是否已存在同名插件
        if existing:
            # manifest 不同，视为版本更新
            if bool(existing.ENABLED):
                self.disable(manifest.id)
            old_path = str(existing.PATH or "")
            if old_path and os.path.exists(old_path) and old_path != target_dir:
                shutil.rmtree(old_path)
            entity = PluginManifestEntity(
                id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                author=manifest.author,
                description=manifest.description,
                category=manifest.category,
                tags=manifest.tags,
                icon=manifest.icon,
                color=manifest.color,
                manifest_json=new_manifest_json,
                enabled=was_enabled,
                path=target_dir,
            )
            ok = self._repo.update_manifest(entity)
            if not ok:
                raise PluginError("插件清单更新数据库失败", errcode=ErrorCode.DATABASE_ERROR, http_status=500)
            log.info(f"[PluginFrameworkService] 插件更新成功: {manifest.id}@{manifest.version}")
        else:
            entity = PluginManifestEntity(
                id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                author=manifest.author,
                description=manifest.description,
                category=manifest.category,
                tags=manifest.tags,
                icon=manifest.icon,
                color=manifest.color,
                manifest_json=JsonUtils.dumps(manifest.to_dict(), ensure_ascii=False),
                enabled=False,
                path=target_dir,
            )
            ok = self._repo.insert_manifest(entity)
            if not ok:
                raise PluginError("插件清单写入数据库失败", errcode=ErrorCode.DATABASE_ERROR, http_status=500)
            log.info(f"[PluginFrameworkService] 插件安装成功: {manifest.id}@{manifest.version}")

        self._plugin_registry.update_manifest_cache(manifest, installed=True)
        if was_enabled:
            # 升级前已启用：更新后恢复启用状态并重新加载，避免插件无感消失
            self.enable(manifest.id)
            threading.Thread(
                target=self._do_enable,
                args=(manifest.id,),
                daemon=True,
            ).start()
        self._get_hook_system().emit("plugin.install", {"plugin_id": manifest.id})
        return manifest

    def uninstall(self, plugin_id: str, purge_data: bool = False) -> None:
        """卸载插件；purge_data=True 时同时删除插件数据目录和日志."""
        lock_key = f"plugin:uninstall:{plugin_id}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            log.info(f"[Plugin]插件卸载正在进行中，跳过: {plugin_id}")
            raise PluginInstallingError("插件卸载正在执行中，请稍后再试")

        try:
            self._do_uninstall(plugin_id, purge_data=purge_data)
        finally:
            lock.release()

    def _do_uninstall(self, plugin_id: str, purge_data: bool = False) -> None:
        """实际卸载逻辑"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise PluginNotInstalledError(f"插件未安装: {plugin_id}")

        old_path = str(orm_model.PATH or "")
        target_dir = old_path
        is_builtin = bool(target_dir and "builtin_plugins" in target_dir)

        if is_builtin:
            # 内置插件软卸载：禁用 + 标记为未安装（不删除文件）
            if bool(orm_model.ENABLED):
                self.disable(plugin_id)
            self._repo.set_manifest_installed(plugin_id, False)
            if purge_data:
                self._purge_plugin_data(plugin_id)
            # 同步更新 Registry 缓存，避免扫描时覆盖数据库

            state = self._plugin_registry.get_state(plugin_id)
            if state:
                state.installed = False
                state.enabled = False
            self._get_hook_system().emit("plugin.uninstall", {"plugin_id": plugin_id})
            log.info(f"[PluginFrameworkService] 内置插件软卸载: {plugin_id}")
            return

        # 第三方插件硬卸载：先让运行时清理，再删除代码和数据
        sandbox = self._plugin_sandbox
        sandbox.unload(plugin_id, purge_data=purge_data)
        if target_dir and os.path.exists(str(target_dir)):
            shutil.rmtree(str(target_dir))
        self._get_hook_system().unregister_all(plugin_id)

        # 删除插件菜单
        self._remove_plugin_menus(plugin_id)

        self._repo.delete_manifest(plugin_id)
        self._repo.delete_config(plugin_id)
        if purge_data:
            self._purge_plugin_data(plugin_id)
        self._plugin_registry.remove_plugin_cache(plugin_id)

        self._get_hook_system().emit("plugin.uninstall", {"plugin_id": plugin_id})
        log.info(f"[PluginFrameworkService] 插件卸载成功: {plugin_id}")

    def _purge_plugin_data(self, plugin_id: str) -> None:
        """删除插件私有数据和日志；不触碰用户订阅/下载/媒体库."""
        data_dir = Path(settings.data_path) / "plugins_data" / plugin_id
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
        with contextlib.suppress(Exception):
            self._repo.clear_logs_by_plugin(plugin_id)
        with contextlib.suppress(Exception):
            self._repo.delete_history_by_plugin(plugin_id)

    def install_market_plugin(self, zip_bytes: bytes, enabled: bool = True) -> dict:
        """市场来源安装：写临时 zip → registry.install（默认禁用落盘）→ 可选启用加载

        返回 {plugin_id, name, version}；安装器已做 sha256/SAST 门禁，这里不再重复。
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="nexus_market_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(zip_bytes)
            manifest = self._plugin_registry.install(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
        if enabled:
            self.enable(manifest.id)
            threading.Thread(target=self._do_enable, args=(manifest.id,), daemon=True).start()
        return {"plugin_id": manifest.id, "name": manifest.name, "version": manifest.version}

    def update_market_plugin(self, zip_bytes: bytes, plugin_id: str) -> dict:
        """市场来源更新：卸载旧实例（配置保留）→ 装新版本 → 启用加载，并清理旧版本目录

        PLUGIN_CONFIG 按 plugin_id 存储且安装不删除，配置天然跨版本保留。
        """
        sandbox = self._plugin_sandbox
        if sandbox.get_plugin_instance(plugin_id) is not None:
            sandbox.unload(plugin_id)
        # registry.install 会 INSERT PLUGIN_MANIFEST（同 id 主键冲突），
        # 更新前先删除旧清单行（配置 PLUGIN_CONFIG 保留，跨版本不删）
        try:
            self._repo.delete_manifest(plugin_id)
        except Exception as e:  # noqa: BLE001
            log.warn(f"[PluginFrameworkService]更新前清理旧清单失败: {e}")
        result = self.install_market_plugin(zip_bytes, enabled=True)
        # 清理同插件旧版本目录（保留配置，仅清文件）
        try:
            base = os.path.join(self._plugins_dir, f"{plugin_id}-")
            new_dir = os.path.join(self._plugins_dir, f"{plugin_id}-{result['version']}")
            for entry in os.listdir(self._plugins_dir):
                entry_path = os.path.join(self._plugins_dir, entry)
                if entry.startswith(base) and os.path.abspath(entry_path) != os.path.abspath(new_dir):
                    shutil.rmtree(entry_path, ignore_errors=True)
        except Exception as e:  # noqa: BLE001
            log.warn(f"[PluginFrameworkService]清理旧版本目录失败: {e}")
        return result

    def _do_enable(self, plugin_id: str) -> None:
        """后台线程执行插件加载和初始化"""
        try:
            log.info(f"[PluginFrameworkService] 开始加载插件: {plugin_id}")
            sandbox = self._plugin_sandbox
            ok = sandbox.load(plugin_id)
            if ok:
                self._get_hook_system().emit("plugin.enable", {"plugin_id": plugin_id})
                log.info(f"[PluginFrameworkService] 插件已启用: {plugin_id}")
            else:
                log.error(f"[PluginFrameworkService] 插件加载返回失败: {plugin_id}")
        except Exception as e:
            log.error(f"[PluginFrameworkService] 插件后台加载异常 {plugin_id}: {e}")

    def refresh_plugin_menus_at_startup(self) -> None:
        """启动时：同步已启用插件的菜单，清理已卸载插件的残留菜单."""
        enabled_ids = self._repo.get_enabled_plugin_ids()
        enabled_codes = {f"Plugin_{pid}" for pid in enabled_ids}

        # 1. 同步已启用插件的菜单
        for plugin_id in enabled_ids:
            self._sync_plugin_menus(plugin_id)

        # 2. 清理已卸载/禁用插件的残留菜单（含插件父菜单）
        parent_menu = self._get_plugin_parent_menu()
        if not parent_menu:
            return
        children = self._menu_repo.get_children_menus(parent_menu.id)
        for child in children:
            if not child.menu_code.startswith("Plugin_"):
                continue
            belongs_to_enabled = any(child.menu_code.startswith(c) for c in enabled_codes)
            if not belongs_to_enabled:
                self._menu_repo.delete_menu(child.id)
                log.info(f"[PluginFrameworkService] 清理残留菜单: {child.menu_code}")

    def enable(self, plugin_id: str) -> None:
        """启用插件（更新数据库和注册表缓存）"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise PluginNotInstalledError(f"插件未安装: {plugin_id}")

        # 首次启用时标记为已安装
        if not getattr(orm_model, "INSTALLED", True):
            self._repo.set_manifest_installed(plugin_id, True)

        self._repo.set_manifest_enabled(plugin_id, True)

        # 同步插件菜单到 RBAC
        self._sync_plugin_menus(plugin_id)

        # 同步更新注册表缓存，否则后台线程加载时缓存仍为 False

        state = self._plugin_registry.get_state(plugin_id)
        if state:
            state.enabled = True
            state.installed = True
        else:
            manifest = self.get_manifest(plugin_id)
            if manifest:
                self._plugin_registry.update_manifest_cache(manifest, enabled=True, installed=True)

    def disable(self, plugin_id: str) -> None:
        """禁用插件"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise PluginNotInstalledError(f"插件未安装: {plugin_id}")

        sandbox = self._plugin_sandbox
        sandbox.unload(plugin_id)
        self._repo.set_manifest_enabled(plugin_id, False)

        # 删除插件菜单
        self._remove_plugin_menus(plugin_id)

        # 同步更新注册表缓存

        state = self._plugin_registry.get_state(plugin_id)
        if state:
            state.enabled = False

        self._get_hook_system().emit("plugin.disable", {"plugin_id": plugin_id})
        log.info(f"[PluginFrameworkService] 插件已禁用: {plugin_id}")

    def get_logs(self, plugin_id: str, page: int = 1, page_size: int = 20) -> dict:
        """获取插件日志"""
        records = self._repo.get_logs_by_plugin(plugin_id, page, page_size)
        total = self._repo.count_logs_by_plugin(plugin_id)

        items = []
        for r in records:
            items.append(
                {
                    "id": r.ID,
                    "level": r.LEVEL,
                    "message": r.MESSAGE,
                    "created_at": r.CREATED_AT,
                }
            )

        return {"total": total, "items": items}

    def clear_logs(self, plugin_id: str) -> None:
        """清空插件日志"""
        self._repo.clear_logs_by_plugin(plugin_id)

    def get_readme(self, plugin_id: str) -> str:
        """获取插件 README"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        plugin_path = str(orm_model.PATH or "") if orm_model else ""
        if not plugin_path:
            return ""

        readme_path = os.path.join(plugin_path, "README.md")
        if not os.path.exists(readme_path):
            return ""

        with open(readme_path, encoding="utf-8") as f:
            return f.read()

    def get_plugin_path(self, plugin_id: str) -> str | None:
        """获取插件目录路径.

        优先使用数据库中记录的安装路径；若该路径已不存在，
        回退到 PluginRegistry 的实时路径解析，避免数据目录变更后插件丢失。
        """
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if orm_model and orm_model.PATH and os.path.exists(orm_model.PATH):
            return str(orm_model.PATH)
        return self._plugin_registry.get_plugin_path(plugin_id)

    def run_plugin(self, plugin_id: str) -> None:
        """异步运行插件，避免 sandbox.load 占用请求线程."""
        threading.Thread(
            target=self._run_plugin_background,
            args=(plugin_id,),
            daemon=True,
            name=f"plugin-run-{plugin_id}",
        ).start()

    def _run_plugin_background(self, plugin_id: str) -> None:
        lock_key = f"plugin:run:{plugin_id}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        if not lock.acquire():
            log.info(f"[Plugin]插件 {plugin_id} 正在运行中，跳过")
            return
        try:
            self._do_run_plugin(plugin_id)
        except Exception as e:  # noqa: BLE001 - 后台任务失败写入日志
            log.error(f"[Plugin]插件 {plugin_id} 运行失败: {e}")
        finally:
            lock.release()

    def _do_run_plugin(self, plugin_id: str) -> None:
        """实际运行插件逻辑（委托 sandbox 进行依赖注入）。"""
        request_client = self.__dict__.get("_request_client") or self.__class__.__dict__.get("_request_client")
        if request_client:
            request_client.close()
        if not self._plugin_sandbox.load(plugin_id):
            raise PluginError(f"插件 {plugin_id} 加载失败", errcode=ErrorCode.PLUGIN_LOAD_FAILED)

        instance = self._plugin_sandbox._instances.get(plugin_id)
        if not instance:
            raise PluginNotInstalledError(f"插件 {plugin_id} 实例不存在")

        if not hasattr(instance, "run"):
            raise PluginError(f"插件 {plugin_id} 未实现 run() 方法")

        threading.Thread(target=instance.run, daemon=True).start()
        log.info(f"[PluginFrameworkService] 插件 {plugin_id} 立即运行任务已启动")

    def reload_plugin(self, plugin_id: str) -> None:
        """异步热重载插件，避免 sandbox.load 占用请求线程."""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise PluginNotInstalledError(f"插件未安装: {plugin_id}")
        threading.Thread(
            target=self._reload_plugin_background,
            args=(plugin_id,),
            daemon=True,
            name=f"plugin-reload-{plugin_id}",
        ).start()

    def _reload_plugin_background(self, plugin_id: str) -> None:
        try:
            if not self._plugin_sandbox.reload(plugin_id):
                log.error(f"[Plugin]插件 {plugin_id} 热重载失败")
        except Exception as e:  # noqa: BLE001 - 后台任务失败写入日志
            log.error(f"[Plugin]插件 {plugin_id} 热重载异常: {e}")
