# -*- coding: utf-8 -*-
"""
Plugin Sandbox - 插件沙箱运行环境
动态加载插件后端模块，提供隔离的运行上下文
"""
import importlib
import importlib.util
import os
import sys
from typing import Any, Dict, Optional

from app.plugin_framework.context import PluginContext
from app.plugin_framework.registry import PluginRegistry
from app.schemas.plugin import PluginManifest
from app.utils.commons import SingletonMeta
import log


class PluginSandbox(metaclass=SingletonMeta):
    """插件沙箱，管理插件后端模块的加载和运行"""

    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self._registry = PluginRegistry()

    def _get_module_path(self, plugin_id: str) -> Optional[str]:
        """根据插件 entry 计算 module_path"""
        manifest = self._registry.get(plugin_id)
        if not manifest or not manifest.backend.entry:
            return None
        return manifest.backend.entry.split(':')[0]

    def _get_plugin_path(self, plugin_id: str) -> Optional[str]:
        """获取插件根目录"""
        return self._registry.get_plugin_path(plugin_id)

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
            if module_path and key.startswith(module_path + '.'):
                to_remove.append(key)
                continue
            # 3. 遗留兼容：plugin_{id} 前缀
            if key.startswith(f"plugin_{plugin_id}"):
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

        try:
            plugin_path = self._get_plugin_path(plugin_id)
            if not plugin_path:
                return False

            entry = manifest.backend.entry
            if not entry:
                log.warn(f"[Sandbox] 插件未声明后端入口: {plugin_id}")
                return False

            module_path, class_name = entry.split(':')
            file_path = os.path.join(plugin_path, module_path.replace('.', '/') + '.py')

            if not os.path.exists(file_path):
                log.error(f"[Sandbox] 插件入口文件不存在: {file_path}")
                return False

            # 动态加载模块
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)
            spec = importlib.util.spec_from_file_location(
                module_path, file_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_path] = module
            spec.loader.exec_module(module)

            PluginClass = getattr(module, class_name)
            if not PluginClass:
                log.error(f"[Sandbox] 插件类未找到: {class_name}")
                return False

            # 创建上下文
            ctx = PluginContext(plugin_id, plugin_name=manifest.name)
            instance = PluginClass(ctx)

            self._instances[plugin_id] = instance

            # 调用生命周期方法
            if hasattr(instance, 'on_enable'):
                instance.on_enable()

            log.info(f"[Sandbox] 插件加载成功: {plugin_id}")
            return True

        except Exception as e:
            log.error(f"[Sandbox] 插件加载失败 {plugin_id}: {e}", exc_info=True)
            return False

    def unload(self, plugin_id: str) -> None:
        """卸载插件"""
        instance = self._instances.get(plugin_id)
        if instance:
            try:
                if hasattr(instance, 'on_disable'):
                    instance.on_disable()
            except Exception as e:
                log.error(f"[Sandbox] 插件禁用失败 {plugin_id}: {e}")

            self._instances.pop(plugin_id, None)
            self._cleanup_modules(plugin_id)
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

    def call_hook(self, plugin_id: str, event: str, data: dict) -> None:
        """调用插件的 hook 处理器"""
        instance = self._instances.get(plugin_id)
        if not instance:
            return

        if hasattr(instance, 'on_hook'):
            try:
                instance.on_hook(event, data)
            except Exception as e:
                log.error(f"[Sandbox] 插件 {plugin_id} 处理 hook {event} 失败: {e}")

    def get_instance(self, plugin_id: str) -> Optional[Any]:
        """获取插件实例"""
        return self._instances.get(plugin_id)

    def load_all(self) -> None:
        """加载所有已启用的插件"""
        for plugin_id, state in self._registry._state_cache.items():
            if state.enabled:
                self.load(plugin_id)
