import os
import pickle
import shutil

import requests

from app.core.constants import SITES_DATA_URL


class SiteDataUpdater:
    """
    sites.dat 数据更新助手
    纯逻辑类，无单例，不持有 Config 状态。
    """

    @staticmethod
    def _download_file(url, dest_path, proxies=None):
        """下载文件并校验"""
        try:
            # 获取GitHub Release信息
            api_response = requests.get(url, timeout=10, proxies=proxies)
            api_response.raise_for_status()
            release_info = api_response.json()

            # 获取实际文件下载URL
            download_url = release_info.get("assets")[0].get("browser_download_url")
            if not download_url:
                raise Exception("未找到下载URL")

            # 下载实际文件内容
            file_response = requests.get(download_url, timeout=30)
            file_response.raise_for_status()

            # 保存文件
            with open(dest_path, "wb") as f:
                f.write(file_response.content)

            return True
        except Exception as e:
            print(f"[Config]下载文件失败: {str(e)}")
            return False

    @staticmethod
    def _get_sites_version(filepath):
        """获取sites.dat版本号"""
        try:
            with open(filepath, "rb") as f:
                data = pickle.load(f)
                return data.get("version", "0")
        except Exception:
            return "0"

    @staticmethod
    def check_sites_update(config_path, temp_path, _inner_config_path, proxies=None):
        """检查并更新sites.dat"""
        try:
            release_url = SITES_DATA_URL
            local_path = os.path.join(os.path.dirname(config_path), "sites.dat")

            # 下载最新文件到临时位置
            temp_file = os.path.join(temp_path, "sites.dat.tmp")
            if not SiteDataUpdater._download_file(release_url, temp_file, proxies=proxies):
                return False

            new_version = SiteDataUpdater._get_sites_version(temp_file)
            current_version = SiteDataUpdater._get_sites_version(local_path) if os.path.exists(local_path) else "0"

            if new_version > current_version:
                shutil.move(temp_file, local_path)
                print(f"[Config]sites.dat 已更新到版本 {new_version}")
            else:
                os.remove(temp_file)
                print(f"[Config]当前版本 {current_version} 已是最新")

            return True
        except Exception as e:
            print(f"[Config]更新sites.dat失败: {str(e)}")
            return False

    @staticmethod
    def update_sites_data(config_path, temp_path, inner_config_path, proxies=None):
        """启动时检查sites.dat更新并复制内置sites.dat"""
        SiteDataUpdater.check_sites_update(config_path, temp_path, inner_config_path, proxies=proxies)
        src_sites = os.path.join(inner_config_path, "sites.dat")
        dst_sites = os.path.join(os.path.dirname(config_path), "sites.dat")
        src_version = SiteDataUpdater._get_sites_version(src_sites)
        dst_version = SiteDataUpdater._get_sites_version(dst_sites) if os.path.exists(dst_sites) else "0"
        if not os.path.exists(dst_sites) or src_version > dst_version:
            shutil.copy2(src_sites, dst_sites)
            print(f"[Config]sites.dat 已更新到版本 {src_version}")
