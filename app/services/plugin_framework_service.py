"""
Plugin Framework Service
插件框架 v2 业务服务层
"""

import json
import os
import shutil
import sys
import threading
import zipfile

import log
from app.db.repositories import PluginFrameworkRepository
from app.db.repositories.rbac_repo_adapter import (
    RBACMenuRepositoryAdapter,
    RBACRoleRepositoryAdapter,
)
from app.domain.entities.plugin import PluginConfigEntity, PluginManifestEntity
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.sandbox import PluginSandbox
from app.schemas.plugin import PluginManifest
from config import Config


class PluginFrameworkService:
    """插件框架业务服务"""

    def __init__(self, repo: PluginFrameworkRepository | None = None):
        self._repo = repo or PluginFrameworkRepository()
        self._menu_repo = RBACMenuRepositoryAdapter()
        self._role_repo = RBACRoleRepositoryAdapter()
        self._plugins_dir = os.path.join(Config().config_path, "plugins")
        if not os.path.exists(self._plugins_dir):
            os.makedirs(self._plugins_dir)

    def _get_plugin_parent_menu(self):
        """获取 Plugin 父菜单"""
        return self._menu_repo.get_menu_by_code("Plugin")

    def _sync_plugin_menus(self, plugin_id: str) -> None:
        """
        为插件 frontend routes 创建 RBAC 菜单，并分配给有 Plugin 权限的角色。
        """
        manifest = self.get_manifest(plugin_id)
        if not manifest or not manifest.frontend or not manifest.frontend.routes:
            return

        parent_menu = self._get_plugin_parent_menu()
        if not parent_menu:
            log.warn("[PluginFrameworkService] Plugin 父菜单不存在，跳过菜单同步")
            return

        new_menu_ids = []
        for idx, route in enumerate(manifest.frontend.routes):
            if not route.menu:
                continue

            # 生成唯一 menu_code
            safe_path = route.path.strip("/").replace("/", "_") or "index"
            menu_code = f"Plugin_{plugin_id}_{safe_path}"

            # 已存在则跳过
            existing = self._menu_repo.get_menu_by_code(menu_code)
            if existing:
                if existing.parent_id != parent_menu.id:
                    # 如果挂错了位置，修正一下
                    self._menu_repo.update_menu(existing.id, parent_id=parent_menu.id, status=1)
                new_menu_ids.append(existing.id)
                continue

            # 计算完整路由路径（与前端 loader.ts 保持一致）
            base_path = f"/plugin/{plugin_id}"
            full_path = route.path if route.path.startswith("/") else f"{base_path}/{route.path}"

            result = self._menu_repo.create_menu(
                menu_name=route.title or manifest.name,
                menu_code=menu_code,
                parent_id=parent_menu.id,
                path=full_path,
                icon=route.icon or manifest.icon or "lucide:puzzle",
                component="",
                sort_order=100 + idx,
                menu_level=2,
                permission_code="plugin:view",
                hide_in_menu=0,
            )
            menu = result if hasattr(result, "id") else self._menu_repo.get_menu_by_code(menu_code)
            if menu:
                new_menu_ids.append(menu.id)
                log.info(f"[PluginFrameworkService] 创建插件菜单: {menu_code} -> {full_path}")

        if new_menu_ids:
            self._assign_menus_to_authorized_roles(new_menu_ids)

    def _remove_plugin_menus(self, plugin_id: str) -> None:
        """
        删除插件对应的 RBAC 菜单。
        """
        parent_menu = self._get_plugin_parent_menu()
        if not parent_menu:
            return

        children = self._menu_repo.get_children_menus(parent_menu.id)
        prefix = f"Plugin_{plugin_id}_"
        removed = 0
        for child in children:
            if child.menu_code.startswith(prefix):
                self._menu_repo.delete_menu(child.id)
                removed += 1
                log.info(f"[PluginFrameworkService] 删除插件菜单: {child.menu_code}")
        if removed:
            log.info(f"[PluginFrameworkService] 共删除 {removed} 个插件菜单")

    def _assign_menus_to_authorized_roles(self, menu_ids: list[int]) -> None:
        """
        将菜单分配给拥有 Plugin 父菜单权限的角色。
        """
        if not menu_ids:
            return

        parent_menu = self._get_plugin_parent_menu()
        if not parent_menu:
            return

        roles = self._role_repo.get_all_roles(status=1)
        for role in roles:
            if not role.menus:
                continue
            # 检查该角色是否拥有 Plugin 父菜单
            has_plugin = any(m.get("menu_code") == "Plugin" or m.get("id") == parent_menu.id for m in role.menus)
            if not has_plugin:
                continue

            # 收集角色当前所有菜单 ID（去重）
            current_ids = {int(mid) for m in role.menus if (mid := m.get("id")) is not None}
            current_ids.update(menu_ids)
            self._role_repo.assign_menus_to_role(role.id, list(current_ids))
            log.info(f"[PluginFrameworkService] 为角色 '{role.role_name}' 分配 {len(menu_ids)} 个插件菜单")

    def list_plugins(self) -> list[dict]:
        """列出所有已安装插件"""
        # 先扫描内置插件（热新增）
        from app.plugin_framework.registry import PluginRegistry

        PluginRegistry().scan()
        orm_list = self._repo.get_all_manifests()
        plugins = []
        for orm_model in orm_list:
            try:
                manifest = PluginManifest.from_dict(json.loads(str(orm_model.MANIFEST_JSON or "{}")))
                plugins.append({
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
                    "installed": bool(getattr(orm_model, "INSTALLED", True)),
                    "supports_run": manifest.backend.supports_run,
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
                            }
                            for r in manifest.frontend.routes
                        ],
                        "slots": [
                            {"target": s.target, "position": s.position, "component": s.component}
                            for s in manifest.frontend.slots
                        ],
                    },
                })
            except Exception as e:
                log.error(f"[PluginFrameworkService] 解析插件清单失败: {e}")
        return plugins

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """获取插件完整 manifest"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            return None
        return PluginManifest.from_dict(json.loads(str(orm_model.MANIFEST_JSON or "{}")))

    def get_config(self, plugin_id: str) -> dict:
        """获取插件配置"""
        orm_model = self._repo.get_config(plugin_id)
        if orm_model and str(orm_model.CONFIG or ""):
            try:
                return json.loads(str(orm_model.CONFIG))
            except Exception:
                pass
        return {}

    def get_config_fields(self, plugin_id: str) -> list[dict]:
        """获取插件配置字段定义"""
        manifest = self.get_manifest(plugin_id)
        fields = []
        if manifest and manifest.frontend and manifest.frontend.settings:
            for f in manifest.frontend.settings.fields:
                fields.append({
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
                })
        return fields

    def save_config(self, plugin_id: str, config: dict) -> None:
        """保存插件配置"""
        entity = PluginConfigEntity(plugin_id=plugin_id, config=config)
        self._repo.save_config(entity)
        HookSystem().emit("plugin.config_changed", {"plugin_id": plugin_id, "config": config})

    def install(self, zip_path: str) -> PluginManifest:
        """安装插件包"""
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"插件包不存在: {zip_path}")

        extract_dir = os.path.join(self._plugins_dir, "__tmp_install")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

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
            raise ValueError("插件包缺少 manifest.json")

        with open(manifest_path, encoding="utf-8") as f:
            manifest_data = json.load(f)

        manifest = PluginManifest.from_dict(manifest_data)
        if not manifest.id or not manifest.name:
            shutil.rmtree(extract_dir)
            raise ValueError("manifest.json 缺少 id 或 name")

        # manifest 所在的真实目录（处理 macOS 压缩的子文件夹情况）
        plugin_root = os.path.dirname(manifest_path)
        target_dir = os.path.join(self._plugins_dir, f"{manifest.id}-{manifest.version}")
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
        existing = self._repo.get_manifest_by_id(manifest.id)
        new_manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False)

        if existing:
            existing_manifest_json = str(existing.MANIFEST_JSON or "{}")
            if existing_manifest_json == new_manifest_json:
                # manifest 完全相同，无需重复安装
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
                log.info(f"[PluginFrameworkService] 插件 {manifest.id} 已存在且 manifest 一致，跳过安装")
                return manifest

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
                enabled=False,
                path=target_dir,
            )
            ok = self._repo.update_manifest(entity)
            if not ok:
                raise RuntimeError("插件清单更新数据库失败")
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
                manifest_json=json.dumps(manifest.to_dict(), ensure_ascii=False),
                enabled=False,
                path=target_dir,
            )
            ok = self._repo.insert_manifest(entity)
            if not ok:
                raise RuntimeError("插件清单写入数据库失败")
            log.info(f"[PluginFrameworkService] 插件安装成功: {manifest.id}@{manifest.version}")

        HookSystem().emit("plugin.install", {"plugin_id": manifest.id})
        return manifest

    def uninstall(self, plugin_id: str) -> None:
        """卸载插件"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise ValueError(f"插件未安装: {plugin_id}")

        old_path = str(orm_model.PATH or "")
        target_dir = old_path
        is_builtin = bool(target_dir and "builtin_plugins" in target_dir)

        if is_builtin:
            # 内置插件软卸载：禁用 + 标记为未安装（不删除文件）
            if bool(orm_model.ENABLED):
                self.disable(plugin_id)
            self._repo.set_manifest_installed(plugin_id, False)
            # 同步更新 Registry 缓存，避免扫描时覆盖数据库
            from app.plugin_framework.registry import PluginRegistry

            state = PluginRegistry().get_state(plugin_id)
            if state:
                state.installed = False
                state.enabled = False
            HookSystem().emit("plugin.uninstall", {"plugin_id": plugin_id})
            log.info(f"[PluginFrameworkService] 内置插件软卸载: {plugin_id}")
            return

        # 第三方插件硬卸载：物理删除
        if target_dir and os.path.exists(str(target_dir)):
            shutil.rmtree(str(target_dir))

        sandbox = PluginSandbox()
        sandbox.unload(plugin_id)
        HookSystem().unregister_all(plugin_id)

        # 删除插件菜单
        self._remove_plugin_menus(plugin_id)

        self._repo.delete_manifest(plugin_id)
        self._repo.delete_config(plugin_id)

        HookSystem().emit("plugin.uninstall", {"plugin_id": plugin_id})
        log.info(f"[PluginFrameworkService] 插件卸载成功: {plugin_id}")

    def _do_enable(self, plugin_id: str) -> None:
        """后台线程执行插件加载和初始化"""
        try:
            log.info(f"[PluginFrameworkService] 开始加载插件: {plugin_id}")
            sandbox = PluginSandbox()
            ok = sandbox.load(plugin_id)
            if ok:
                HookSystem().emit("plugin.enable", {"plugin_id": plugin_id})
                log.info(f"[PluginFrameworkService] 插件已启用: {plugin_id}")
            else:
                log.error(f"[PluginFrameworkService] 插件加载返回失败: {plugin_id}")
        except Exception as e:
            log.error(f"[PluginFrameworkService] 插件后台加载异常 {plugin_id}: {e}")

    def enable(self, plugin_id: str) -> None:
        """启用插件（更新数据库和注册表缓存）"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise ValueError(f"插件未安装: {plugin_id}")

        # 首次启用时标记为已安装
        if not getattr(orm_model, "INSTALLED", True):
            self._repo.set_manifest_installed(plugin_id, True)

        self._repo.set_manifest_enabled(plugin_id, True)

        # 同步插件菜单到 RBAC
        self._sync_plugin_menus(plugin_id)

        # 同步更新注册表缓存，否则后台线程加载时缓存仍为 False
        from app.plugin_framework.registry import PluginRegistry

        state = PluginRegistry().get_state(plugin_id)
        if state:
            state.enabled = True
            state.installed = True

    def disable(self, plugin_id: str) -> None:
        """禁用插件"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise ValueError(f"插件未安装: {plugin_id}")

        sandbox = PluginSandbox()
        sandbox.unload(plugin_id)
        self._repo.set_manifest_enabled(plugin_id, False)

        # 删除插件菜单
        self._remove_plugin_menus(plugin_id)

        # 同步更新注册表缓存
        from app.plugin_framework.registry import PluginRegistry

        state = PluginRegistry().get_state(plugin_id)
        if state:
            state.enabled = False

        HookSystem().emit("plugin.disable", {"plugin_id": plugin_id})
        log.info(f"[PluginFrameworkService] 插件已禁用: {plugin_id}")

    def get_logs(self, plugin_id: str, page: int = 1, page_size: int = 20) -> dict:
        """获取插件日志"""
        records = self._repo.get_logs_by_plugin(plugin_id, page, page_size)
        total = self._repo.count_logs_by_plugin(plugin_id)

        items = []
        for r in records:
            items.append({
                "id": r.ID,
                "level": r.LEVEL,
                "message": r.MESSAGE,
                "created_at": r.CREATED_AT,
            })

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
        """获取插件目录路径"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            return None
        return str(orm_model.PATH)

    def run_plugin(self, plugin_id: str) -> None:
        """立即运行插件（临时加载并调用 run 方法）"""
        import importlib.util

        from app.plugin_framework.context import PluginContext

        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise ValueError(f"插件未安装: {plugin_id}")

        manifest = PluginManifest.from_dict(json.loads(str(orm_model.MANIFEST_JSON or "{}")))
        entry = manifest.backend.entry
        if not entry:
            raise ValueError(f"插件未声明后端入口: {plugin_id}")

        plugin_path = str(orm_model.PATH or "")
        if not plugin_path or not os.path.exists(plugin_path):
            raise ValueError(f"插件路径不存在: {plugin_id}")

        module_path, class_name = entry.split(":")
        file_path = os.path.join(plugin_path, module_path.replace(".", "/") + ".py")

        if not os.path.exists(file_path):
            raise ValueError(f"插件入口文件不存在: {file_path}")

        # 强制清理模块缓存，确保加载最新代码
        to_remove = [k for k in list(sys.modules.keys()) if k == module_path or k.startswith(module_path + ".")]
        for k in to_remove:
            del sys.modules[k]
        importlib.invalidate_caches()

        # 临时将插件根目录加入 sys.path，使 backend/_autobackup 等子模块可解析
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)

        spec = importlib.util.spec_from_file_location(module_path, file_path)
        if not spec or not spec.loader:
            raise ValueError(f"无法加载插件模块: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_path] = module
        spec.loader.exec_module(module)

        plugin_class = getattr(module, class_name)
        ctx = PluginContext(plugin_id, plugin_name=manifest.name)
        instance = plugin_class(ctx)

        if not hasattr(instance, "run"):
            raise ValueError(f"插件 {plugin_id} 未实现 run() 方法")

        threading.Thread(target=instance.run, daemon=True).start()
        log.info(f"[PluginFrameworkService] 插件 {plugin_id} 立即运行任务已启动")

    def reload_plugin(self, plugin_id: str) -> None:
        """热重载插件（清理缓存后重新加载）"""
        orm_model = self._repo.get_manifest_by_id(plugin_id)
        if not orm_model:
            raise ValueError(f"插件未安装: {plugin_id}")

        sandbox = PluginSandbox()
        if not sandbox.reload(plugin_id):
            raise RuntimeError(f"插件 {plugin_id} 热重载失败")
