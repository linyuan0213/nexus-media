"""
MovieLike Plugin v2
媒体服务器中用户将电影设为最爱时，自动转移到精选文件夹
"""

import os

from app.plugin_framework.context import PluginContext
from app.utils import SystemUtils
from app.utils.config_tools import update_favtype
from app.utils.types import MediaType
from app.di import container


class MovieLikePlugin:
    """电影精选插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._mediaserver = container.media_server()
        self._filetransfer = container.filetransfer_service()
        self._category = container.category()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("电影精选插件已启用")

    def on_disable(self):
        self.ctx.info("电影精选插件已禁用")

    def on_hook(self, event, data):
        if event == "webhook.emby":
            self._fav_transfer(data or {})

    def _fav_transfer(self, event_data):
        config = self._get_config()
        if not config.get("enable"):
            return

        dir_name = config.get("dir_name", "精选")
        if dir_name:
            update_favtype(dir_name)

        if self._mediaserver.get_type() != "emby":
            return

        action_type = event_data.get("Event")
        if action_type != "item.rate":
            return

        if event_data.get("Item", {}).get("Type") != "Movie":
            return

        item_path = event_data.get("Item", {}).get("Path")
        if not item_path:
            return

        local_path = config.get("local_path")
        remote_path = config.get("remote_path")
        local_path2 = config.get("local_path2")
        remote_path2 = config.get("remote_path2")
        local_path3 = config.get("local_path3")
        remote_path3 = config.get("remote_path3")

        if local_path and remote_path and item_path.startswith(remote_path):
            item_path = item_path.replace(remote_path, local_path).replace("\\", "/")
        if local_path2 and remote_path2 and item_path.startswith(remote_path2):
            item_path = item_path.replace(remote_path2, local_path2).replace("\\", "/")
        if local_path3 and remote_path3 and item_path.startswith(remote_path3):
            item_path = item_path.replace(remote_path3, local_path3).replace("\\", "/")

        if not os.path.exists(item_path):
            self.ctx.warn(f"{item_path} 文件不存在")
            return

        if os.path.isdir(item_path):
            movie_dir = item_path
        else:
            movie_dir = os.path.dirname(item_path)

        movie_type = os.path.basename(os.path.dirname(movie_dir))
        if movie_type == dir_name:
            return
        if movie_type not in self._category.movie_categorys:
            return

        movie_name = os.path.basename(movie_dir)
        movie_path = self._filetransfer.get_best_target_path(mtype=MediaType.MOVIE, in_path=movie_dir)
        org_path = os.path.join(movie_path or "", movie_type, movie_name)
        new_path = os.path.join(movie_path or "", dir_name, movie_name)

        if os.path.exists(org_path):
            self.ctx.info(f"开始转移文件 {org_path} 到 {new_path} ...")
            if os.path.exists(new_path):
                self.ctx.info(f"目录 {new_path} 已存在")
                return
            ret, retmsg = SystemUtils.move(org_path, new_path)
            if ret != 0:
                self.ctx.error(f"{retmsg}")
            else:
                from app.plugin_framework.hook_system import HookSystem

                HookSystem().emit("media.library_synced", {"dest": new_path, "media_info": {}})
        else:
            self.ctx.warn(f"{org_path} 目录不存在")
