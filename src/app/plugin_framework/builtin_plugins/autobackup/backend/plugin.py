"""
AutoBackup Plugin v2
自动备份 Nexus Media 数据和配置文件
"""

import contextlib
import glob
import os
import time

from app.core.settings import settings
from app.plugin_framework.context import PluginContext
from app.services.system_service import backup as do_backup
from app.utils import SystemUtils
from app.utils.path_utils import get_temp_path
from ._autobackup.filestorage_client import FileClientFactory


class AutoBackupPlugin:
    """自动备份插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def _get_config(self):
        """读取全部配置"""
        return self.ctx.get_config() or {}

    def on_enable(self):
        """启用插件"""
        self.ctx.info("自动备份插件已启用")
        self._start_service()

    def on_disable(self):
        """禁用插件"""
        self.ctx.info("自动备份插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        """事件处理"""
        if event == "plugin.config_changed" and data.get("plugin_id") == self.ctx.plugin_id:
            self.ctx.info("配置已变更，重载服务")
            self._stop_service()
            self._start_service()

    def run(self):
        """立即运行备份"""
        self.ctx.info("手动触发备份")
        self._do_backup()

    def _start_service(self):
        """启动备份服务"""
        config = self._get_config()
        enabled = config.get("enabled", False)
        cron = config.get("cron")

        self.ctx.info(f"_start_service: enabled={enabled}, cron={cron}")

        if not enabled:
            self.ctx.info("未启用，跳过")
            return

        # 周期运行
        if enabled and cron:
            self.ctx.info(f"定时备份服务启动，周期：{cron}")
            try:
                self.ctx.schedule_cron("backup", self._do_backup, cron=cron)
            except Exception as e:
                self.ctx.error(f"schedule_cron 失败: {e}")

    def _stop_service(self):
        """停止备份服务"""
        with contextlib.suppress(Exception):
            self.ctx.remove_schedule("backup")

    def _do_backup(self):
        """执行备份"""
        config = self._get_config()
        storage_type = config.get("storage_type", "local")
        full = config.get("full", False)
        cnt = config.get("cnt")
        bk_path_cfg = config.get("bk_path")
        remote_path = config.get("remote_path", "")
        notify = config.get("notify", False)
        base_url = config.get("base_url")
        username = config.get("username")
        password = config.get("password")
        share_name = config.get("share_name")

        self.ctx.info(f"当前时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))} 开始备份")

        # 确定本地备份路径
        if storage_type == "local":
            if SystemUtils.is_docker():
                bk_path = os.path.join(settings.config_path, "backup_file")
            else:
                bk_path = bk_path_cfg or os.path.join(settings.config_path, "backup_file")
        else:
            bk_path = os.path.join(get_temp_path(), "backup_temp")
            os.makedirs(bk_path, exist_ok=True)

        # 生成备份文件
        zip_file = do_backup(bk_path=bk_path, full_backup=bool(full))
        if not zip_file:
            self.ctx.error("创建备份失败")
            return

        del_count = 0
        bk_count = 0

        # 远程存储处理
        if storage_type in ["webdav", "samba"]:
            try:
                client = FileClientFactory.create_client(
                    client_type=storage_type,
                    base_url=base_url,
                    username=username,
                    password=password,
                    share_name=share_name,
                )
                if not client:
                    raise Exception("无法创建客户端实例")

                remote_dir = remote_path.strip("/")
                remote_file = os.path.basename(zip_file)
                remote_target = f"{remote_dir}/{remote_file}" if remote_dir else remote_file

                self.ctx.info(f"上传备份文件到远程：{remote_target}")
                client.upload_file(zip_file, remote_target)

                os.remove(zip_file)
                self.ctx.info(f"已删除本地临时文件：{zip_file}")

                # 清理旧备份
                if cnt:
                    max_keep = int(cnt)
                    files = client.list_files(remote_dir)
                    backup_files = [f for f in files if f and "bk_" in f and f.endswith(".zip")]
                    bk_count = len(backup_files)
                    sorted_files = sorted(backup_files)
                    if len(sorted_files) > max_keep:
                        del_count = len(sorted_files) - max_keep
                        for file in sorted_files[:del_count]:
                            client.delete_file(file)
                            self.ctx.info(f"已删除远程备份：{file}")

            except Exception as e:
                self.ctx.error(f"远程备份失败：{e!s}")
                if os.path.exists(zip_file):
                    os.remove(zip_file)
                return
        else:
            # 本地存储清理旧备份
            if cnt:
                files = sorted(glob.glob(os.path.join(bk_path, "bk*")), key=os.path.getctime)
                bk_count = len(files)
                if len(files) > int(cnt):
                    del_count = len(files) - int(cnt)
                    for i in range(del_count):
                        os.remove(files[i])
                        self.ctx.info(f"已删除本地备份：{files[i]}")

        # 发送通知
        if notify:
            self.ctx.notify(
                title="[自动备份任务完成]",
                text=(
                    f"创建备份{'成功' if zip_file else '失败'}\n"
                    f"清理备份数量 {del_count}\n"
                    f"剩余备份数量 {bk_count - del_count}"
                ),
            )
