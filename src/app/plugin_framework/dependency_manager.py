"""
插件依赖管理器
负责解析和安装插件所需的第三方 Python 包
"""

import os
import subprocess

import log


class PluginDependencyManager:
    """插件依赖管理器"""

    @staticmethod
    def install_dependencies(
        dependencies: list[str],
        plugin_id: str,
        plugin_path: str | None = None,
    ) -> tuple[bool, str]:
        """
        安装插件依赖

        :param dependencies: 依赖列表，格式如 ["requests>=2.28.0", "numpy"]
        :param plugin_id: 插件 ID（用于日志）
        :param plugin_path: 插件目录路径（用于读取 requirements.txt fallback）
        :return: (是否成功, 错误信息)
        """
        reqs: list[str] = []

        # 1. 优先使用 manifest 中声明的 dependencies
        if dependencies:
            reqs.extend(dependencies)

        # 2. fallback：读取插件目录下的 requirements.txt
        if plugin_path and not reqs:
            req_file = os.path.join(plugin_path, "requirements.txt")
            if os.path.exists(req_file):
                with open(req_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            reqs.append(line)

        if not reqs:
            return True, ""

        # 过滤已安装的依赖
        missing = [r for r in reqs if not PluginDependencyManager.check_dependency(r)]
        if not missing:
            log.info(f"[PluginDeps] 插件 {plugin_id} 所有依赖已满足")
            return True, ""

        log.info(f"[PluginDeps] 插件 {plugin_id} 需要安装依赖: {missing}")

        # 3. 使用 uv pip install 安装缺失依赖
        cmd = ["uv", "pip", "install", "--python", ".venv/bin/python"] + missing
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode != 0:
                err = result.stderr or result.stdout or "未知错误"
                log.error(f"[PluginDeps] 插件 {plugin_id} 依赖安装失败: {err}")
                return False, err

            log.info(f"[PluginDeps] 插件 {plugin_id} 依赖安装成功")
            return True, ""
        except subprocess.TimeoutExpired:
            log.error(f"[PluginDeps] 插件 {plugin_id} 依赖安装超时")
            return False, "依赖安装超时"
        except FileNotFoundError:
            log.error("[PluginDeps] uv 命令未找到，无法安装插件依赖")
            return False, "uv 命令未找到，请确保 uv 已安装"
        except Exception as e:
            log.error(f"[PluginDeps] 插件 {plugin_id} 依赖安装异常: {e}")
            return False, str(e)

    @staticmethod
    def check_dependency(package_spec: str) -> bool:
        """检查单个依赖是否已安装"""
        pkg_name = package_spec.split("[")[0].split("=")[0].split("<")[0].split(">")[0].strip()
        try:
            __import__(pkg_name.replace("-", "_"))
            return True
        except ImportError:
            return False

    @staticmethod
    def check_dependencies(dependencies: list[str]) -> dict[str, bool]:
        """批量检查依赖是否已安装"""
        return {dep: PluginDependencyManager.check_dependency(dep) for dep in dependencies}
