"""
站点配置远程更新服务

从 nexus-media-sites 仓库 release 自动拉取最新站点配置，
解压到用户配置目录的 sites/ 子目录，实现站点配置热更新。
"""

import os
import shutil
import tempfile
import zipfile
from typing import Any

import requests

import log
from app.core.config import Config
from app.utils.config_tools import get_proxies


class SiteConfigUpdater:
    """站点配置更新器"""

    _RELEASE_API_URL = "https://api.github.com/repos/linyuan0213/nexus-media-sites/releases/latest"
    _ASSET_NAME = "sites-config.zip"
    _VERSION_FILE = "version"
    _REQUIRED_SUBDIRS = ("api", "html", "schema")

    def __init__(self, config_dir: str | None = None):
        if config_dir is None:
            cfg = Config()
            config_dir = os.path.dirname(cfg.config_path) if cfg.config_path else None
        self._config_dir = config_dir or "/config"
        self._sites_dir = os.path.join(self._config_dir, "sites")
        self._version_file = os.path.join(self._sites_dir, self._VERSION_FILE)

    def _read_local_version(self) -> str:
        try:
            with open(self._version_file, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return "0"

    def _write_local_version(self, version: str) -> None:
        os.makedirs(self._sites_dir, exist_ok=True)
        with open(self._version_file, "w", encoding="utf-8") as f:
            f.write(version)

    def _fetch_remote_info(self, proxies: dict | None = None) -> dict[str, Any] | None:
        try:
            headers = {"Accept": "application/vnd.github.v3+json"}
            resp = requests.get(self._RELEASE_API_URL, headers=headers, timeout=15, proxies=proxies)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warn(f"【SiteConfigUpdater】查询远程版本失败: {e!s}")
            return None

    def _find_asset_url(self, release_info: dict) -> str | None:
        assets = release_info.get("assets", [])
        for asset in assets:
            if asset.get("name") == self._ASSET_NAME:
                return asset.get("browser_download_url")
        tag = release_info.get("tag_name", "")
        if tag:
            return (
                f"https://github.com/linyuan0213/nexus-media-sites/releases/download/"
                f"{tag}/{self._ASSET_NAME}"
            )
        return None

    @staticmethod
    def _download_file(url: str, dest: str, proxies: dict | None = None) -> bool:
        try:
            resp = requests.get(url, timeout=60, stream=True, proxies=proxies)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            log.warn(f"【SiteConfigUpdater】下载文件失败: {e!s}")
            return False

    @staticmethod
    def _extract_zip(zip_path: str, dest_dir: str) -> bool:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest_dir)
            return True
        except Exception as e:
            log.warn(f"【SiteConfigUpdater】解压失败: {e!s}")
            return False

    def _validate_sites_dir(self, directory: str) -> bool:
        for sub in self._REQUIRED_SUBDIRS:
            if not os.path.isdir(os.path.join(directory, sub)):
                log.warn(f"【SiteConfigUpdater】目录结构异常，缺少 {sub}/")
                return False
        has_json = any(
            f.endswith(".json")
            for root, _, files in os.walk(directory)
            for f in files
        )
        if not has_json:
            log.warn("【SiteConfigUpdater】目录中未找到任何站点定义文件")
            return False
        return True

    def get_version_info(self) -> dict[str, Any]:
        local = self._read_local_version()
        remote_info = self._fetch_remote_info()
        remote = remote_info.get("tag_name", "unknown") if remote_info else "unknown"
        return {"local": local, "remote": remote, "needs_update": remote != "unknown" and remote != local}

    def update(self, force: bool = False) -> dict[str, Any]:
        proxies = get_proxies()
        release_info = self._fetch_remote_info(proxies)
        if not release_info:
            return {"success": False, "message": "查询远程版本失败", "version": self._read_local_version()}

        remote_version = release_info.get("tag_name", "unknown")
        local_version = self._read_local_version()

        if not force and remote_version == local_version:
            return {"success": True, "message": f"当前已是最新版本 {local_version}", "version": local_version}

        asset_url = self._find_asset_url(release_info)
        if not asset_url:
            return {"success": False, "message": "未找到站点配置下载地址", "version": local_version}

        tmp_zip = tempfile.mktemp(suffix=".zip")
        if not self._download_file(asset_url, tmp_zip, proxies):
            return {"success": False, "message": "下载站点配置失败", "version": local_version}

        tmp_extract = tempfile.mkdtemp(prefix="sites_")
        if not self._extract_zip(tmp_zip, tmp_extract):
            os.remove(tmp_zip)
            shutil.rmtree(tmp_extract, ignore_errors=True)
            return {"success": False, "message": "解压站点配置失败", "version": local_version}

        if not self._validate_sites_dir(tmp_extract):
            os.remove(tmp_zip)
            shutil.rmtree(tmp_extract, ignore_errors=True)
            return {"success": False, "message": "站点配置格式校验失败", "version": local_version}

        try:
            if os.path.exists(self._sites_dir):
                backup_dir = f"{self._sites_dir}.backup"
                shutil.rmtree(backup_dir, ignore_errors=True)
                shutil.move(self._sites_dir, backup_dir)
            shutil.move(tmp_extract, self._sites_dir)
            self._write_local_version(remote_version)
            log.info(f"【SiteConfigUpdater】站点配置已更新到 {remote_version}")
        except Exception as e:
            log.error(f"【SiteConfigUpdater】替换配置失败: {e!s}")
            return {"success": False, "message": f"替换配置失败: {e!s}", "version": local_version}
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            if os.path.exists(tmp_extract):
                shutil.rmtree(tmp_extract, ignore_errors=True)

        return {"success": True, "message": f"已更新到 {remote_version}", "version": remote_version}

    def ensure_local_sites(self, builtin_sites_dir: str) -> str:
        os.makedirs(self._sites_dir, exist_ok=True)
        has_valid_config = any(
            os.path.isdir(os.path.join(self._sites_dir, sub)) and os.listdir(os.path.join(self._sites_dir, sub))
            for sub in ("api", "html")
        )
        if not has_valid_config and os.path.isdir(builtin_sites_dir):
            log.info("【SiteConfigUpdater】本地站点配置不存在，从内置目录复制...")
            for sub in ("api", "html", "schema"):
                src = os.path.join(builtin_sites_dir, sub)
                dst = os.path.join(self._sites_dir, sub)
                if os.path.isdir(src) and not os.path.exists(dst):
                    shutil.copytree(src, dst)
            self._write_local_version("builtin")
            log.info("【SiteConfigUpdater】内置站点配置已复制到本地")
        return self._sites_dir


def update_site_config_at_startup() -> None:
    try:
        updater = SiteConfigUpdater()
        info = updater.get_version_info()
        if info.get("needs_update"):
            log.info(f"【SiteConfigUpdater】发现新版本 {info['remote']}，开始自动更新...")
            result = updater.update()
            if result["success"]:
                log.info(f"【SiteConfigUpdater】{result['message']}")
            else:
                log.warn(f"【SiteConfigUpdater】{result['message']}")
        else:
            log.info(f"【SiteConfigUpdater】当前站点配置版本: {info['local']}，无需更新")
    except Exception as e:
        log.warn(f"【SiteConfigUpdater】启动时自动更新失败: {e!s}")
