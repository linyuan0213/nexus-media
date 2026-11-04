"""
Plugin Sandbox - 插件沙箱运行环境
动态加载插件后端模块，提供隔离的运行上下文
"""

import contextlib
import importlib
import importlib.util
import inspect
import os
import sys
import types
from typing import Any

import log
from app.core.exceptions import PluginError
from app.indexer.contract.http import HttpIndexerProvider
from app.infrastructure.image_proxy.referer_registry import image_referer_registry
from app.media.metadata.registry import registry as metadata_registry
from app.media.scraper.processor_registry import scraper_processor_registry
from app.message import Message
from app.message.template_registry import message_template_registry
from app.plugin_framework import api_registry
from app.plugin_framework.context import PluginContext
from app.plugin_framework.dependency_manager import PluginDependencyManager
from app.plugin_framework.registry import PluginRegistry


class PluginSandbox:
    """插件沙箱，管理插件后端模块的加载和运行.

    由 lifespan 通过 AppContext 创建并管理生命周期。
    """

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        message: Message,
        scheduler_core: Any,
        hook_system: Any,
        site_engine: Any,
        media_service: Any,
        plugin_log_repo: Any | None = None,
        site_cache: Any | None = None,
        downloader_core: Any | None = None,
        media_server: Any | None = None,
        subscribe_service: Any | None = None,
        searcher: Any | None = None,
        sync_engine: Any | None = None,
        site_resolver: Any | None = None,
        indexer_helper: Any | None = None,
        agent_service: Any | None = None,
        filetransfer_service: Any | None = None,
        site_service: Any | None = None,
        event_bus: Any | None = None,
        app_context: Any | None = None,
    ):
        self._instances: dict[str, Any] = {}
        self._contexts: dict[str, Any] = {}
        self._registry = plugin_registry
        self._message = message
        self._scheduler_core = scheduler_core
        self._hook_system = hook_system
        self._site_engine = site_engine
        self._media_service = media_service
        self._plugin_log_repo = plugin_log_repo
        self._site_cache = site_cache
        self._downloader_core = downloader_core
        self._media_server = media_server
        self._subscribe_service = subscribe_service
        self._searcher = searcher
        self._sync_engine = sync_engine
        self._site_resolver = site_resolver
        self._indexer_helper = indexer_helper
        self._agent_service = agent_service
        self._filetransfer_service = filetransfer_service
        self._site_service = site_service
        self._event_bus = event_bus
        self._app_context = app_context

    @staticmethod
    def _filter_kwargs(plugin_class: Any, deps: dict[str, Any]) -> dict[str, Any]:
        """根据插件类构造函数的参数名过滤依赖。"""
        try:
            params = inspect.signature(plugin_class.__init__).parameters
        except (TypeError, ValueError):
            return {}
        return {k: v for k, v in deps.items() if k in params}

    def _get_module_path(self, plugin_id: str) -> str | None:
        """根据插件 entry 计算 module_path"""
        manifest = self._registry.get(plugin_id)
        if not manifest or not manifest.backend.entry:
            return None
        return manifest.backend.entry.split(":")[0]

    def _get_plugin_path(self, plugin_id: str) -> str | None:
        """获取插件根目录"""
        return self._registry.get_plugin_path(plugin_id)

    @staticmethod
    def _unique_root(plugin_id: str) -> str:
        """每个插件使用独立顶层包，避免多个插件的 backend 包互相覆盖."""
        return "plugin_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in plugin_id)

    @staticmethod
    def _uses_absolute_backend_import(plugin_path: str, entry_root: str) -> bool:
        """检测插件是否仍使用 backend.* 绝对导入（旧插件兼容）."""
        root = os.path.join(plugin_path, entry_root)
        if not os.path.isdir(root):
            return False
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, name), encoding="utf-8", errors="ignore") as handle:
                        for line in handle:
                            text = line.lstrip()
                            if text.startswith(f"from {entry_root}") or text.startswith(f"import {entry_root}"):
                                return True
                except OSError:
                    continue
        return False

    def _install_entry_root_alias(self, entry_root: str, root_dir: str) -> None:
        """旧插件绝对导入兼容：把 backend 指向当前插件目录，隔离其它插件缓存."""
        for key in list(sys.modules):
            if key != entry_root and not key.startswith(entry_root + "."):
                continue
            module_file = getattr(sys.modules.get(key), "__file__", None) or ""
            module_paths = getattr(sys.modules.get(key), "__path__", None) or []
            belongs = bool(module_file and os.path.abspath(module_file).startswith(os.path.abspath(root_dir) + os.sep))
            belongs = belongs or any(
                os.path.abspath(str(item)).startswith(os.path.abspath(root_dir) + os.sep) for item in module_paths
            )
            if not belongs:
                del sys.modules[key]
        if entry_root not in sys.modules:
            package = types.ModuleType(entry_root)
            package.__path__ = [root_dir]
            package.__package__ = entry_root
            sys.modules[entry_root] = package
        else:
            sys.modules[entry_root].__path__ = [root_dir]

    def _install_plugin_package(self, plugin_id: str, plugin_path: str, module_path: str) -> str:
        """为插件创建唯一包路径，返回入口模块完整名称."""
        unique_root = self._unique_root(plugin_id)
        for key in list(sys.modules):
            if key == unique_root or key.startswith(unique_root + "."):
                del sys.modules[key]
        root_pkg = types.ModuleType(unique_root)
        root_pkg.__path__ = [plugin_path]
        root_pkg.__package__ = unique_root
        sys.modules[unique_root] = root_pkg

        current_path = plugin_path
        parts = module_path.split(".")
        for index, part in enumerate(parts[:-1], start=1):
            current_path = os.path.join(current_path, part)
            name = f"{unique_root}." + ".".join(parts[:index])
            package = types.ModuleType(name)
            package.__path__ = [current_path]
            package.__package__ = name
            sys.modules[name] = package
        return f"{unique_root}.{module_path}"

    def _cleanup_modules(self, plugin_id: str) -> None:
        """清理插件相关的 sys.modules 缓存"""
        module_path = self._get_module_path(plugin_id)
        plugin_path = self._get_plugin_path(plugin_id)

        # 收集需要清理的模块名
        to_remove = []
        for key in list(sys.modules.keys()):
            # 1. 精确匹配入口模块
            if module_path and key == module_path:
                to_remove.append(key)
                continue
            # 2. 入口模块的子模块（backend.xxx）
            if module_path and key.startswith(module_path + "."):
                to_remove.append(key)
                continue
            # 3. 唯一插件包前缀
            if key.startswith(self._unique_root(plugin_id)):
                to_remove.append(key)
                continue
            # 4. 入口顶层包（仅清理指向当前插件目录的旧绝对导入缓存）
            entry_root = (module_path or "").split(".", 1)[0]
            if entry_root and (key == entry_root or key.startswith(entry_root + ".")):
                module_file = getattr(sys.modules.get(key), "__file__", None) or ""
                module_paths = getattr(sys.modules.get(key), "__path__", None) or []
                belongs = bool(
                    plugin_path
                    and module_file
                    and os.path.abspath(module_file).startswith(os.path.abspath(plugin_path) + os.sep)
                )
                belongs = belongs or any(
                    plugin_path and os.path.abspath(str(item)).startswith(os.path.abspath(plugin_path) + os.sep)
                    for item in module_paths
                )
                if belongs:
                    to_remove.append(key)
                continue
            # 5. 模块文件位于当前插件目录
            module_file = getattr(sys.modules.get(key), "__file__", None) or ""
            if plugin_path and module_file.startswith(os.path.abspath(plugin_path) + os.sep):
                to_remove.append(key)

        for key in to_remove:
            try:
                del sys.modules[key]
                log.debug(f"[Sandbox] 清理模块缓存: {key}")
            except KeyError:
                pass

        # 从 sys.path 移除插件根目录（下次 load 会重新插入）
        if plugin_path and plugin_path in sys.path:
            sys.path.remove(plugin_path)

        # 使 importlib 缓存失效
        importlib.invalidate_caches()

    def load(self, plugin_id: str) -> bool:
        """加载并初始化插件后端"""
        manifest = self._registry.get(plugin_id)
        if not manifest:
            log.error(f"[Sandbox] 插件未找到: {plugin_id}")
            return False

        state = self._registry.get_state(plugin_id)
        if not state:
            log.error(f"[Sandbox] 插件状态未找到: {plugin_id}")
            return False
        if not state.enabled:
            log.info(f"[Sandbox] 插件未启用，跳过加载: {plugin_id}")
            return False

        # 加载前安装 manifest 声明的依赖（缺失时才安装，幂等）
        deps = manifest.backend.dependencies
        if deps:
            ok, err = PluginDependencyManager.install_dependencies(dependencies=deps, plugin_id=plugin_id)
            if not ok:
                log.error(f"[Sandbox] 插件 {plugin_id} 依赖安装失败: {err}")
                if self._plugin_log_repo is not None:
                    try:
                        self._plugin_log_repo.insert(plugin_id, "ERROR", f"依赖安装失败: {err}")
                    except Exception:  # noqa: S110 - 日志写入失败不影响主流程
                        pass
                return False

        try:
            plugin_path = self._get_plugin_path(plugin_id)
            if not plugin_path:
                return False

            entry = manifest.backend.entry
            if not entry:
                log.warn(f"[Sandbox] 插件未声明后端入口: {plugin_id}")
                return False

            module_path, class_name = entry.split(":")
            file_path = os.path.join(plugin_path, module_path.replace(".", "/") + ".py")

            if not os.path.exists(file_path):
                log.error(f"[Sandbox] 插件入口文件不存在: {file_path}")
                return False

            # 动态加载模块：每个插件使用唯一包名，避免 backend 包互相覆盖。
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)
            entry_root = module_path.split(".", 1)[0]
            if entry_root:
                root_dir = os.path.join(plugin_path, entry_root)
                if self._uses_absolute_backend_import(plugin_path, entry_root):
                    self._install_entry_root_alias(entry_root, root_dir)
            full_module_name = self._install_plugin_package(plugin_id, plugin_path, module_path)
            spec = importlib.util.spec_from_file_location(full_module_name, file_path)
            if not spec or not spec.loader:
                log.error(f"[Sandbox] 无法加载插件模块: {module_path}")
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[full_module_name] = module
            spec.loader.exec_module(module)

            plugin_class = getattr(module, class_name)
            if not plugin_class:
                log.error(f"[Sandbox] 插件类未找到: {class_name}")
                return False

            # 创建上下文
            ctx = PluginContext(
                plugin_id,
                plugin_name=manifest.name,
                plugin_log_repo=self._plugin_log_repo,
                message=self._message,
                scheduler_core=self._scheduler_core,
                hook_system=self._hook_system,
                site_engine=self._site_engine,
                media_service=self._media_service,
                metadata_service=getattr(self._app_context, "metadata_service", None),
                manifest_metadata=manifest.backend.metadata,
                filter_service=getattr(self._app_context, "filter_service", None),
                discovery_service=getattr(self._app_context, "discovery_service", None),
            )
            deps = {
                "sites": self._site_cache,
                "site_resolver": self._site_resolver,
                "index_helper": self._indexer_helper,
                "mediaserver": self._media_server,
                "downloader": self._downloader_core,
                "searcher": self._searcher,
                "subscribe": self._subscribe_service,
                "site_cache": self._site_cache,
                "agent_service": self._agent_service,
                "sync": self._sync_engine,
                "filetransfer": self._filetransfer_service,
                "site_service": self._site_service,
                "event_bus": self._event_bus,
                "app_context": self._app_context,
            }
            instance = plugin_class(ctx, **self._filter_kwargs(plugin_class, deps))

            self._instances[plugin_id] = instance
            self._contexts[plugin_id] = ctx
            self._load_manifest_metadata(ctx, plugin_id, plugin_path, manifest)

            # 注册 manifest 声明的事件钩子
            hooks = getattr(manifest.backend, "hooks", None) or []
            for event in hooks:
                if event:
                    self._hook_system.register(event, plugin_id)

            # 调用生命周期方法
            if hasattr(instance, "on_enable"):
                instance.on_enable()

            log.info(f"[Sandbox] 插件加载成功: {plugin_id}")
            return True

        except PluginError as e:
            log.error(f"[Sandbox] 插件加载失败 {plugin_id}: {e}")
            self.unload(plugin_id, uninstalling=False)
            return False
        except Exception as e:  # noqa: BLE001
            log.error(f"[Sandbox] 插件加载失败 {plugin_id}: {e}")
            self.unload(plugin_id, uninstalling=False)
            return False

    def _load_manifest_metadata(self, ctx, plugin_id: str, plugin_path: str, manifest) -> None:
        """按 manifest 的 backend.metadata 自动实例化并注册 provider/profile."""
        metadata = getattr(manifest.backend, "metadata", None)
        if metadata is None:
            return
        specs = (
            ("providers", ctx.register_metadata_provider),
            ("discovery_providers", ctx.register_discovery_provider),
            ("indexer_providers", ctx.register_indexer_provider),
            ("content_profiles", lambda key, obj: ctx.register_metadata_profile("content", key, obj)),
            ("match_profiles", lambda key, obj: ctx.register_metadata_profile("match", key, obj)),
            ("parser_profiles", lambda key, obj: ctx.register_metadata_profile("parser", key, obj)),
            ("naming_profiles", lambda key, obj: ctx.register_metadata_profile("naming", key, obj)),
            ("nfo_profiles", lambda key, obj: ctx.register_metadata_profile("nfo", key, obj)),
        )
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)
        for field, register in specs:
            for item in getattr(metadata, field, []) or []:
                key = item.get("key")
                entry = item.get("entry")
                if not key:
                    continue
                if field == "indexer_providers" and item.get("type") == "http":
                    try:
                        config = ctx.get_config() or {}
                        base_url = str(config.get("base_url") or "").strip()
                        if not base_url:
                            continue
                        register(
                            key,
                            HttpIndexerProvider(
                                base_url,
                                token=config.get("token") or None,
                                timeout=float(config.get("timeout") or 30),
                                provider_id=key,
                                icon=str(item.get("icon") or getattr(manifest, "icon", "") or ""),
                                info_path=str(config.get("info_path") or "/api/indexer/info"),
                                search_path=str(config.get("search_path") or "/api/indexer/search"),
                                list_path=str(config.get("list_path") or "/api/indexer/list"),
                            ),
                        )
                        log.info(f"[Sandbox]索引器已注册 {plugin_id}: {key}")
                    except Exception as exc:  # noqa: BLE001
                        log.warn(f"[Sandbox]索引器注册失败 {plugin_id} {key}: {exc}")
                    continue
                if not entry:
                    continue
                try:
                    module_name, class_name = entry.split(":", 1)
                    module = importlib.import_module(module_name)
                    target = getattr(module, class_name)
                    register(key, target())
                    log.info(f"[Sandbox]元数据扩展已注册 {plugin_id}: {field}/{key}")
                except Exception as exc:  # noqa: BLE001 - 单个扩展失败不影响插件
                    log.warn(f"[Sandbox]元数据扩展注册失败 {plugin_id} {field}/{key}: {exc}")
        message_template_registry.register_pack(
            plugin_id,
            getattr(metadata, "message_templates", None),
            getattr(metadata, "message_labels", None),
        )
        image_referer_registry.register_pack(
            plugin_id,
            getattr(metadata, "image_referers", None),
        )

    def unload(self, plugin_id: str, purge_data: bool = False, *, uninstalling: bool = False) -> None:
        """卸载插件；只有真正卸载时才调用 on_uninstall."""
        ctx = self._contexts.pop(plugin_id, None)
        if ctx is not None:
            with contextlib.suppress(Exception):
                ctx.unregister_all_metadata()

        instance = self._instances.get(plugin_id)
        if instance:
            if uninstalling and hasattr(instance, "on_uninstall"):
                try:
                    instance.on_uninstall(purge_data)
                except Exception as exc:  # noqa: BLE001 - 清理失败不阻断卸载
                    log.warn(f"[Sandbox] 插件卸载清理失败 {plugin_id}: {exc}")
            try:
                if hasattr(instance, "on_disable"):
                    instance.on_disable()
            except Exception as e:  # noqa: BLE001 - 单个钩子失败不能阻断资源清理
                log.error(f"[Sandbox] 插件禁用失败 {plugin_id}: {e}")

            self._instances.pop(plugin_id, None)
            self._cleanup_modules(plugin_id)

            # 注销该插件的所有事件钩子
            self._hook_system.unregister_all(plugin_id)

            # 注销该插件的所有自定义 API 与公开回调
            api_registry.unregister_plugin_all(plugin_id)

            # 注销该插件注册的元数据 provider / 发现来源 / profile
            metadata_registry.unregister_plugin(plugin_id)
            message_template_registry.unregister_plugin(plugin_id)
            scraper_processor_registry.unregister_plugin(plugin_id)
            image_referer_registry.unregister_plugin(plugin_id)

            # 自动注销该插件的所有消息命令
            self._message.clear_plugin_commands(plugin_id)

            log.info(f"[Sandbox] 插件卸载: {plugin_id}")

    def reload(self, plugin_id: str) -> bool:
        """热重载插件：清理缓存后重新加载"""
        manifest = self._registry.get(plugin_id)
        if not manifest:
            log.error(f"[Sandbox] 重载失败，插件未找到: {plugin_id}")
            return False

        log.info(f"[Sandbox] 开始热重载插件: {plugin_id}")

        # 1. 卸载现有实例
        self.unload(plugin_id)

        # 2. 强制清理所有模块缓存
        self._cleanup_modules(plugin_id)

        # 3. 重新加载
        ok = self.load(plugin_id)
        if ok:
            log.info(f"[Sandbox] 插件热重载成功: {plugin_id}")
        else:
            log.error(f"[Sandbox] 插件热重载失败: {plugin_id}")
        return ok

    def call(self, plugin_id: str, method: str, *args, **kwargs) -> Any:
        """调用插件方法"""
        instance = self._instances.get(plugin_id)
        if not instance:
            raise RuntimeError(f"插件未加载: {plugin_id}")

        func = getattr(instance, method, None)
        if not func:
            raise AttributeError(f"插件 {plugin_id} 没有方法: {method}")

        return func(*args, **kwargs)

    def call_hook(self, plugin_id: str, event: str, data: dict | None = None) -> None:
        """调用插件的 hook 处理器"""
        instance = self._instances.get(plugin_id)
        if not instance:
            return

        if hasattr(instance, "on_hook"):
            try:
                instance.on_hook(event, data)
            except PluginError as e:
                log.error(f"[Sandbox] 插件 {plugin_id} 处理 hook {event} 失败: {e}")

    def get_plugin_instance(self, plugin_id: str) -> Any | None:
        """获取插件实例"""
        return self._instances.get(plugin_id)

    def load_all(self) -> None:
        """加载所有已启用的插件，批量注册消息命令并统一刷新菜单。"""
        command_manager = getattr(self._message, "_command_manager", None)
        with command_manager.suppress_refresh() if command_manager else contextlib.nullcontext():
            for plugin_id, state in self._registry._state_cache.items():
                if state.enabled:
                    self.load(plugin_id)
