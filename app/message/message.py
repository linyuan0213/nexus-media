import json
import re
import time
from enum import Enum

from jinja2 import BaseLoader, Environment

import log
from app.core.module_config import ModuleConf
from app.db.repositories import ConfigRepository
from app.helper.thread_helper import ThreadHelper
from app.infrastructure.queue import MessageQueueFactory
from app.message.client_registry import ClientRegistry
from app.message.message_center import MessageCenter
from app.message.templates import DEFAULT_MESSAGE_TEMPLATES
from app.utils import ExceptionUtils, StringUtils
from app.utils.commons import SingletonMeta
from app.utils.config_tools import get_domain
from app.utils.types import MediaType, SearchType
from app.utils.web_utils import WebUtils


def _filesize_filter(value):
    """Jinja2 filter: 格式化文件大小"""
    if value is None:
        return ""
    return StringUtils.str_filesize(value) if value else ""


def _datetime_filter(value, format_str="%Y-%m-%d %H:%M:%S"):
    """Jinja2 filter: 格式化日期时间"""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        return time.strftime(format_str, time.localtime(value))
    if isinstance(value, str):
        # 尝试解析时间戳
        try:
            timestamp = float(value)
            return time.strftime(format_str, time.localtime(timestamp))
        except (ValueError, TypeError):
            return value
    return str(value)


def _default_filter(value, default_value=""):
    """Jinja2 filter: 默认值处理"""
    if value is None or value == "":
        return default_value
    return value


def _yesno_filter(value, yes="是", no="否"):
    """Jinja2 filter: 布尔值转换为是/否"""
    if value is True:
        return yes
    elif value is False:
        return no
    return no


def _truncatestr_filter(value, length=100, suffix="..."):
    """Jinja2 filter: 截断字符串"""
    if not value:
        return ""
    value = str(value)
    if len(value) <= length:
        return value
    return value[: length - len(suffix)] + suffix


def _striptags_filter(value):
    """Jinja2 filter: 去除HTML标签"""
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", str(value))


def _parse_client_config(client_config) -> dict:
    config = {}
    if client_config.CONFIG:
        try:
            config = json.loads(client_config.CONFIG)
        except json.JSONDecodeError:
            log.error(f"【Message】客户端 {client_config.NAME} 的CONFIG不是有效JSON: {client_config.CONFIG}")
    config.update({"interactive": client_config.INTERACTIVE})
    templates = {}
    if client_config.TEMPLATES:
        try:
            templates = json.loads(client_config.TEMPLATES)
        except json.JSONDecodeError:
            log.error(f"【Message】客户端 {client_config.NAME} 的模板配置不是有效的JSON: {client_config.TEMPLATES}")
    switchs = []
    if client_config.SWITCHS:
        try:
            parsed = json.loads(client_config.SWITCHS)
            if isinstance(parsed, list):
                switchs = parsed
            elif isinstance(parsed, str):
                all_keys = set(ModuleConf.MESSAGE_CONF.get("switch", {}).keys())
                switchs = [s.strip() for s in parsed.split(",") if s.strip() and s.strip() in all_keys]
        except json.JSONDecodeError:
            raw = str(client_config.SWITCHS)
            all_keys = set(ModuleConf.MESSAGE_CONF.get("switch", {}).keys())
            switchs = [s.strip() for s in raw.split(",") if s.strip() and s.strip() in all_keys]
    return {
        "id": client_config.ID,
        "name": client_config.NAME,
        "type": client_config.TYPE,
        "config": config,
        "switchs": switchs,
        "interactive": client_config.INTERACTIVE,
        "enabled": client_config.ENABLED,
        "templates": templates,
    }


class Message(metaclass=SingletonMeta):
    config_repo = None
    messagecenter = None
    _active_clients = []
    _active_interactive_clients = {}
    _client_configs = {}
    _domain = None
    _queue = None
    _loaded = False
    # 插件注册的消息命令：{cmd: {"plugin_id": str, "desc": str, "func": callable}}
    _plugin_commands: dict = {}

    @property
    def active_clients(self):
        self._ensure_loaded()
        return self._active_clients

    @property
    def active_interactive_clients(self):
        self._ensure_loaded()
        return self._active_interactive_clients

    def __init__(self):
        self._queue = MessageQueueFactory.create()
        self._queue.register_handler(self._handle_queued_message)
        self.config_repo = ConfigRepository()
        self.messagecenter = MessageCenter()
        self._domain = get_domain()

    def _handle_queued_message(self, title, text, image, url, user_id, client_id, client_type):
        """队列消息处理器：通过 client_id 找到 client 并发送"""
        client = None
        for c in self.active_clients:
            if str(c.get("id")) == client_id:
                client = c
                break
        if client:
            self._do_sendmsg(client, title, text, image, url, user_id)
        else:
            log.warn(f"【Message】队列中找不到客户端: id={client_id}, type={client_type}")

    def _ensure_loaded(self):
        if self._loaded:
            return
        for client_config in self.config_repo.get_message_client() or []:
            if client_config.ENABLED and client_config.CONFIG:
                self._add_client_from_config(client_config)
        self._loaded = True

    def _add_client_from_config(self, client_config):
        cid = str(client_config.ID)
        self._remove_client(cid)
        config = _parse_client_config(client_config)
        self._client_configs[cid] = config
        client_entry = {
            "id": client_config.ID,
            "name": client_config.NAME,
            "type": client_config.TYPE,
            "config": config["config"],
            "switchs": config["switchs"],
            "interactive": client_config.INTERACTIVE,
            "enabled": client_config.ENABLED,
            "templates": config["templates"],
            "search_type": ModuleConf.MESSAGE_CONF.get("client").get(client_config.TYPE, {}).get("search_type"),
            "max_length": ModuleConf.MESSAGE_CONF.get("client").get(client_config.TYPE, {}).get("max_length"),
            "client": ClientRegistry.build(ctype=client_config.TYPE, conf=config["config"]),
        }
        client_instance = client_entry["client"]
        if hasattr(client_instance, "setup"):
            ThreadHelper().start_thread(client_instance.setup, ())
        self._active_clients.append(client_entry)
        if client_config.INTERACTIVE:
            self._active_interactive_clients[client_entry["search_type"]] = client_entry
        # 保险机制：如果已有插件命令，立即刷新菜单
        if self._plugin_commands and hasattr(client_instance, "refresh_menu"):
            try:
                client_instance.refresh_menu()
            except Exception as e:
                log.warn(f"【Message】客户端 {client_config.TYPE} 初始菜单刷新失败: {e}")

    def _remove_client(self, cid):
        cid = str(cid)
        self._active_clients = [c for c in self._active_clients if str(c.get("id")) != cid]
        keys_to_remove = [k for k, v in self._active_interactive_clients.items() if str(v.get("id")) == cid]
        for k in keys_to_remove:
            del self._active_interactive_clients[k]
        if cid in self._client_configs:
            del self._client_configs[cid]

    def _refresh_client(self, cid):
        self._ensure_loaded()
        client_config = self._get_client_config_by_id(cid)
        if not client_config:
            self._remove_client(cid)
            return
        if client_config.ENABLED and client_config.CONFIG:
            self._add_client_from_config(client_config)
        else:
            self._remove_client(str(cid))
            self._client_configs[str(cid)] = _parse_client_config(client_config)

    def _get_client_config_by_id(self, cid):
        for config in self.config_repo.get_message_client() or []:
            if str(config.ID) == str(cid):
                return config
        return None

    # ---------- 消息命令管理 ----------

    def register_command(self, cmd: str, desc: str, func, plugin_id: str = "") -> None:
        """注册消息命令（系统或插件均可调用）"""
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        self._plugin_commands[cmd] = {"plugin_id": plugin_id, "desc": desc, "func": func}
        log.info(f"【Message】命令注册: {cmd} ({desc})")
        self._refresh_client_menus()

    def unregister_command(self, cmd: str) -> None:
        """注销消息命令"""
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        if cmd in self._plugin_commands:
            del self._plugin_commands[cmd]
            log.info(f"【Message】命令注销: {cmd}")
            self._refresh_client_menus()

    def clear_plugin_commands(self, plugin_id: str) -> None:
        """清空指定插件的所有命令"""
        to_remove = [cmd for cmd, info in self._plugin_commands.items() if info.get("plugin_id") == plugin_id]
        for cmd in to_remove:
            del self._plugin_commands[cmd]
        if to_remove:
            log.info(f"【Message】插件 {plugin_id} 命令已清除: {to_remove}")
            self._refresh_client_menus()

    def get_commands(self) -> dict:
        """获取所有消息命令（系统命令 + 插件命令）"""
        from app.message.commands import COMMANDS

        all_cmds = dict(COMMANDS)
        for cmd, info in self._plugin_commands.items():
            all_cmds[cmd] = info.get("desc", "")
        return all_cmds

    def get_plugin_commands(self) -> dict:
        """获取插件命令"""
        return self._plugin_commands.copy()

    def refresh_menus(self) -> None:
        """公开方法：通知所有交互式客户端刷新菜单"""
        self._refresh_client_menus()

    def _refresh_client_menus(self) -> None:
        """通知所有交互式客户端刷新菜单"""
        self._ensure_loaded()
        found = 0
        for client_entry in self._active_clients:
            client = client_entry.get("client")
            ctype = client_entry.get("type", "unknown")
            if client and hasattr(client, "refresh_menu"):
                found += 1
                try:
                    client.refresh_menu()
                except Exception as e:
                    log.warn(f"【Message】刷新 {ctype} 菜单失败: {e}")
        if found:
            log.info(f"【Message】菜单刷新完成，{found} 个客户端已更新")

    def __render_template(self, template_str, variables):
        """
        使用Jinja2渲染模板
        :param template_str: 模板字符串
        :param variables: 变量字典
        :return: 渲染后的字符串，如果渲染失败则返回None
        """
        if not template_str:
            return None
        try:
            env = Environment(loader=BaseLoader())
            # 添加自定义过滤器
            env.filters["filesize"] = _filesize_filter
            env.filters["datetime"] = _datetime_filter
            env.filters["default"] = _default_filter
            env.filters["yesno"] = _yesno_filter
            env.filters["truncatestr"] = _truncatestr_filter
            env.filters["striptags"] = _striptags_filter
            template = env.from_string(template_str)
            result = template.render(**variables)
            # 处理转义字符（JSON中的\n需要转换为实际的换行符）
            result = result.replace("\\n", "\n")
            return result
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【Message】模板渲染失败：{str(e)}")
            return None

    def __apply_client_template(self, client, msg_type, variables):
        """
        应用客户端模板
        :param client: 客户端配置
        :param msg_type: 消息类型，如 'download_start', 'transfer_finished' 等
        :param variables: 模板变量字典
        :return: (title, text) 渲染后的标题和内容，如果无模板则返回 (None, None)
        """
        client_name = client.get("name", "未知")
        templates = client.get("templates")

        log.debug(f"【Message】客户端 {client_name} 模板配置: {templates}")

        # 如果 templates 是字符串，尝试解析为 JSON
        if isinstance(templates, str):
            try:
                templates = json.loads(templates)
                log.debug(f"【Message】客户端 {client_name} 模板配置已解析为字典")
            except json.JSONDecodeError as e:
                log.error(f"【Message】客户端 {client_name} 模板配置 JSON 解析失败: {e}")
                return None, None

        if not templates or not isinstance(templates, dict):
            log.debug(f"【Message】客户端 {client_name} 没有模板配置或格式不正确, 类型: {type(templates)}")
            return None, None

        template_config = templates.get(msg_type)
        log.debug(f"【Message】客户端 {client_name} 消息类型 {msg_type} 的模板: {template_config}")

        if not template_config or not isinstance(template_config, dict):
            log.debug(f"【Message】客户端 {client_name} 没有 {msg_type} 类型的自定义模板，尝试使用默认模板")
            template_config = DEFAULT_MESSAGE_TEMPLATES.get(msg_type)
            if not template_config:
                log.debug(f"【Message】消息类型 {msg_type} 没有默认模板")
                return None, None

        title_template = template_config.get("title")
        text_template = template_config.get("text")

        log.debug(f"【Message】客户端 {client_name} 标题模板: {title_template}")
        log.debug(f"【Message】客户端 {client_name} 内容模板: {text_template}")

        rendered_title = self.__render_template(title_template, variables) if title_template else None
        rendered_text = self.__render_template(text_template, variables) if text_template else None

        log.info(
            f"【Message】客户端 {client_name} 模板渲染结果 - 标题: {rendered_title is not None}, 内容: {rendered_text is not None}"
        )

        return rendered_title, rendered_text

    def get_status(self, ctype=None, config=None):
        """
        测试消息设置状态
        """
        if not config or not ctype:
            return False
        # 测试状态不启动监听服务
        state, ret_msg = ClientRegistry.build(ctype=ctype, conf=config).send_msg(
            title="测试", text="这是一条测试消息", url="https://github.com/linyuan0213/nas-tools"
        )
        if not state:
            log.error(f"【Message】{ctype} 发送测试消息失败：%s" % ret_msg)
        return state

    def _do_sendmsg(self, client, title, text, image, url, user_id):
        """实际执行消息发送（由队列调用）"""
        if not client or not client.get("client"):
            log.warning("【Message】客户端对象为空，跳过发送")
            return
        cname = client.get("name")
        log.info(f"【Message】开始发送消息 {cname}：title={title}")
        if self._domain:
            if url:
                if "/open?url=" in url:
                    url = f"{self._domain}{url}"
                elif not url.startswith("http"):
                    url = f"{self._domain}?next={url}"
            else:
                url = ""
        else:
            url = ""
        max_length = client.get("max_length")
        texts = StringUtils.split_text(text, max_length) if max_length else [text]
        for txt in texts:
            cur_title = title if title else txt
            cur_text = "" if not title else txt
            state, ret_msg = client.get("client").send_msg(
                title=cur_title, text=cur_text, image=image, url=url, user_id=user_id
            )
            if not state:
                log.error(f"【Message】{cname} 消息发送失败：%s" % ret_msg)
                raise RuntimeError(ret_msg)
        log.info(f"【Message】消息发送成功 {cname}：title={title}")

    def __sendmsg(self, client, title, text="", image="", url="", user_id="", msg_type=None, variables=None):
        """
        通用消息发送（异步入队）
        :param client: 消息端
        :param title: 消息标题
        :param text: 消息内容
        :param image: 图片URL
        :param url: 消息跳转地址
        :param user_id: 用户ID，如有则只发给这个用户
        :param msg_type: 消息类型，用于模板匹配
        :param variables: 模板变量字典
        :return: 是否成功入队
        """
        if not client or not client.get("client"):
            return False
        if msg_type and variables:
            template_title, template_text = self.__apply_client_template(client, msg_type, variables)
            title = template_title if template_title is not None else title
            text = template_text if template_text is not None else text
        cname = client.get("name")
        log.info(f"【Message】消息入队 {cname}：title={title}")
        return self._queue.submit(self._do_sendmsg, client, title, text, image, url, user_id, name=f"sendmsg:{cname}")

    def send_channel_msg(self, channel, title, text="", image="", url="", user_id=""):
        """
        按渠道发送消息，用于消息交互
        :param channel: 消息渠道
        :param title: 消息标题
        :param text: 消息内容
        :param image: 图片URL
        :param url: 消息跳转地址
        :param user_id: 用户ID，如有则只发给这个用户
        :return: 发送状态、错误信息
        """
        # 插入消息中心
        if channel == SearchType.WEB:
            self.messagecenter.insert_system_message(title=title, content=text)
            return True
        # 发送消息
        client = self.active_interactive_clients.get(channel)
        if client:
            state = self.__sendmsg(client=client, title=title, text=text, image=image, url=url, user_id=user_id)
            return state
        return False

    def _do_send_list_msg(self, client, medias, user_id, title):
        """实际执行列表消息发送（由队列调用）"""
        if not client or not client.get("client"):
            log.warning("【Message】客户端对象为空，跳过列表发送")
            return
        cname = client.get("name")
        log.info(f"【Message】开始发送列表消息 {cname}：title={title}")
        state, ret_msg = client.get("client").send_list_msg(
            medias=medias, user_id=user_id, title=title, url=self._domain
        )
        if not state:
            log.error(f"【Message】{cname} 发送列表消息失败：%s" % ret_msg)
            raise RuntimeError(ret_msg)
        log.info(f"【Message】列表消息发送成功 {cname}：title={title}")

    def __send_list_msg(self, client, medias, user_id, title):
        """
        发送选择类消息（异步入队）
        """
        if not client or not client.get("client"):
            return False
        cname = client.get("name")
        log.info(f"【Message】列表消息入队 {cname}：title={title}")
        return self._queue.submit(self._do_send_list_msg, client, medias, user_id, title, name=f"send_list_msg:{cname}")

    def send_channel_list_msg(self, channel, title, medias: list, user_id=""):
        """
        发送列表选择消息，用于消息交互
        :param channel: 消息渠道
        :param title: 消息标题
        :param medias: 媒体信息列表
        :param user_id: 用户ID，如有则只发给这个用户
        :return: 发送状态、错误信息
        """
        if channel == SearchType.WEB:
            texts = []
            index = 1
            for media in medias:
                texts.append(f"{index}. {media.get_title_string()}，{media.get_vote_string()}")
                index += 1
            self.messagecenter.insert_system_message(title=title, content="\n".join(texts))
            return True
        client = self.active_interactive_clients.get(channel)
        if client:
            state = self.__send_list_msg(client=client, title=title, medias=medias, user_id=user_id)
            return state
        return False

    def send_download_message(self, in_from: SearchType, can_item, download_setting_name=None, downloader_name=None):
        """
        发送下载的消息
        :param in_from: 下载来源
        :param can_item: 下载的媒体信息
        :param download_setting_name: 下载设置名称
        :param downloader_name: 下载器名称
        :return: 发送状态、错误信息
        """
        # 默认消息
        msg_title = f"{can_item.get_title_ep_string()} 开始下载"
        msg_text = f"{can_item.get_star_string()}"
        msg_text = f"{msg_text}\n来自：{in_from.value}"
        if download_setting_name:
            msg_text = f"{msg_text}\n下载设置：{download_setting_name}"
        if downloader_name:
            msg_text = f"{msg_text}\n下载器：{downloader_name}"
        if can_item.user_name:
            msg_text = f"{msg_text}\n用户：{can_item.user_name}"
        if can_item.site:
            if in_from == SearchType.USERRSS:
                msg_text = f"{msg_text}\n任务：{can_item.site}"
            else:
                msg_text = f"{msg_text}\n站点：{can_item.site}"
        if can_item.get_resource_type_string():
            msg_text = f"{msg_text}\n质量：{can_item.get_resource_type_string()}"
        if can_item.size:
            if str(can_item.size).isdigit():
                size = StringUtils.str_filesize(can_item.size)
            else:
                size = can_item.size
            msg_text = f"{msg_text}\n大小：{size}"
        if can_item.org_string:
            msg_text = f"{msg_text}\n种子：{can_item.org_string}"
        if can_item.seeders:
            msg_text = f"{msg_text}\n做种数：{can_item.seeders}"
        msg_text = f"{msg_text}\n促销：{can_item.get_volume_factor_string()}"
        if can_item.hit_and_run:
            msg_text = f"{msg_text}\nHit&Run：是"
        if can_item.description:
            html_re = re.compile(r"<[^>]+>", re.S)
            description = html_re.sub("", can_item.description)
            can_item.description = re.sub(r"<[^>]+>", "", description)
            msg_text = f"{msg_text}\n描述：{can_item.description}"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=msg_title, content=msg_text)
        # 发送消息
        for client in self.active_clients:
            if "download_start" in client.get("switchs"):
                # 准备模板变量 - 提供更丰富的字段
                # 计算文件大小字符串
                size_str = StringUtils.str_filesize(can_item.size) if can_item.size else ""
                # 处理描述文本（去除HTML标签）
                description_clean = ""
                if can_item.description:
                    description_clean = re.sub(r"<[^>]+>", "", can_item.description)

                variables = {
                    "item": can_item,
                    "in_from": in_from,
                    "download_setting_name": download_setting_name or "",
                    "downloader_name": downloader_name or "",
                    # 常用字段直接暴露
                    "title": can_item.title or can_item.get_name() or "",
                    "year": can_item.year or "",
                    "season": can_item.get_season_string() if hasattr(can_item, "get_season_string") else "",
                    "episode": can_item.get_episode_string() if hasattr(can_item, "get_episode_string") else "",
                    "site": can_item.site or "",
                    "size": can_item.size or 0,
                    "size_str": size_str,
                    "seeders": can_item.seeders or 0,
                    "peers": can_item.peers or 0,
                    "org_string": can_item.org_string or "",
                    "description": description_clean,
                    "description_raw": can_item.description or "",
                    "resource_type": can_item.get_resource_type_string()
                    if hasattr(can_item, "get_resource_type_string")
                    else "",
                    "volume_factor": can_item.get_volume_factor_string()
                    if hasattr(can_item, "get_volume_factor_string")
                    else "未知",
                    "hit_and_run": can_item.hit_and_run or False,
                    "user_name": can_item.user_name or "",
                    "page_url": can_item.page_url or "",
                    "vote_average": can_item.vote_average or 0,
                    "star_string": can_item.get_star_string() if hasattr(can_item, "get_star_string") else "",
                    "title_ep_string": can_item.get_title_ep_string()
                    if hasattr(can_item, "get_title_ep_string")
                    else "",
                    "title_string": can_item.get_title_string() if hasattr(can_item, "get_title_string") else "",
                }
                # 应用模板
                template_title, template_text = self.__apply_client_template(client, "download_start", variables)
                # 使用模板渲染结果或默认消息
                final_title = template_title if template_title is not None else msg_title
                final_text = template_text if template_text is not None else msg_text
                self.__sendmsg(
                    client=client,
                    title=final_title,
                    text=final_text,
                    image=can_item.get_message_image(),
                    url="downloading",
                )

    def send_transfer_movie_message(self, in_from: Enum, media_info, exist_filenum, category_flag):
        """
        发送转移电影的消息
        :param in_from: 转移来源
        :param media_info: 转移的媒体信息
        :param exist_filenum: 已存在的文件数
        :param category_flag: 二级分类开关
        :return: 发送状态、错误信息
        """
        msg_title = f"{media_info.get_title_string()} 已入库"
        if media_info.vote_average:
            msg_str = f"{media_info.get_vote_string()}，类型：电影"
        else:
            msg_str = "类型：电影"
        if media_info.category:
            if category_flag:
                msg_str = f"{msg_str}，类别：{media_info.category}"
        if media_info.get_resource_type_string():
            msg_str = f"{msg_str}，质量：{media_info.get_resource_type_string()}"
        msg_str = f"{msg_str}，大小：{StringUtils.str_filesize(media_info.size)}，来自：{in_from.value}"
        if exist_filenum != 0:
            msg_str = f"{msg_str}，{exist_filenum}个文件已存在"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=msg_title, content=msg_str)
        # 发送消息
        for client in self.active_clients:
            if "transfer_finished" in client.get("switchs"):
                variables = {
                    "media_info": media_info,
                    "in_from": in_from,
                    "exist_filenum": exist_filenum,
                    "category_flag": category_flag,
                }
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="history",
                    msg_type="transfer_finished",
                    variables=variables,
                )

    def send_transfer_tv_message(self, message_medias: dict, in_from: Enum):
        """
        发送转移电视剧/动漫的消息
        """
        for item_info in message_medias.values():
            if item_info.total_episodes == 1:
                msg_title = f"{item_info.get_title_string()} {item_info.get_season_episode_string()} 已入库"
            else:
                msg_title = f"{item_info.get_title_string()} {item_info.get_season_string()} 共{item_info.total_episodes}集 已入库"
            if item_info.vote_average:
                msg_str = f"{item_info.get_vote_string()}，类型：{item_info.type.value}"
            else:
                msg_str = f"类型：{item_info.type.value}"
            if item_info.category:
                msg_str = f"{msg_str}，类别：{item_info.category}"
            if item_info.total_episodes == 1:
                msg_str = f"{msg_str}，大小：{StringUtils.str_filesize(item_info.size)}，来自：{in_from.value}"
            else:
                msg_str = f"{msg_str}，总大小：{StringUtils.str_filesize(item_info.size)}，来自：{in_from.value}"
            # 插入消息中心
            self.messagecenter.insert_system_message(title=msg_title, content=msg_str)
            # 发送消息
        for client in self.active_clients:
            if "transfer_finished" in client.get("switchs"):
                variables = {
                    "media_info": item_info,
                    "in_from": in_from,
                    "total_episodes": item_info.total_episodes if hasattr(item_info, "total_episodes") else 1,
                    "season_episode": item_info.get_season_episode_string()
                    if hasattr(item_info, "get_season_episode_string")
                    else "",
                }
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=item_info.get_message_image(),
                    url="history",
                    msg_type="transfer_finished",
                    variables=variables,
                )

    def send_download_fail_message(self, item, error_msg):
        """
        发送下载失败的消息
        """
        title = f"添加下载任务失败：{item.get_title_string()} {item.get_season_episode_string()}"
        text = f"站点：{item.site}\n种子名称：{item.org_string}\n种子链接：{item.enclosure}\n错误信息：{error_msg}"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "download_fail" in client.get("switchs"):
                variables = {
                    "item": item,
                    "error_msg": error_msg,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=item.get_message_image(),
                    msg_type="download_fail",
                    variables=variables,
                )

    def send_rss_success_message(self, in_from: Enum, media_info):
        """
        发送订阅成功的消息
        """
        if media_info.type == MediaType.MOVIE:
            msg_title = f"{media_info.get_title_string()} 已添加订阅"
        else:
            msg_title = f"{media_info.get_title_string()} {media_info.get_season_string()} 已添加订阅"
        msg_str = f"类型：{media_info.type.value}"
        if media_info.vote_average:
            msg_str = f"{msg_str}，{media_info.get_vote_string()}"
        msg_str = f"{msg_str}，来自：{in_from.value}"
        if media_info.user_name:
            msg_str = f"{msg_str}，用户：{media_info.user_name}"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=msg_title, content=msg_str)
        # 发送消息
        for client in self.active_clients:
            if "rss_added" in client.get("switchs"):
                variables = {
                    "media_info": media_info,
                    "in_from": in_from,
                }
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="movie_rss" if media_info.type == MediaType.MOVIE else "tv_rss",
                    msg_type="rss_added",
                    variables=variables,
                )

    def send_rss_finished_message(self, media_info):
        """
        发送订阅完成的消息，只针对电视剧
        """
        if media_info.type == MediaType.MOVIE:
            return
        else:
            if media_info.over_edition:
                msg_title = f"{media_info.get_title_string()} {media_info.get_season_string()} 已完成洗版"
            else:
                msg_title = f"{media_info.get_title_string()} {media_info.get_season_string()} 已完成订阅"
        msg_str = f"类型：{media_info.type.value}"
        if media_info.vote_average:
            msg_str = f"{msg_str}，{media_info.get_vote_string()}"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=msg_title, content=msg_str)
        # 发送消息
        for client in self.active_clients:
            if "rss_finished" in client.get("switchs"):
                variables = {
                    "media_info": media_info,
                    "over_edition": media_info.over_edition if hasattr(media_info, "over_edition") else False,
                }
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url="downloaded",
                    msg_type="rss_finished",
                    variables=variables,
                )

    def send_site_signin_message(self, msgs: list):
        """
        发送站点签到消息
        """
        if not msgs:
            return
        title = "站点签到"
        text = "\n".join(msgs)
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "site_signin" in client.get("switchs"):
                variables = {
                    "msgs": msgs,
                }
                self.__sendmsg(client=client, title=title, text=text, msg_type="site_signin", variables=variables)

    def send_site_message(self, title=None, text=None):
        """
        发送站点消息
        """
        if not title:
            return
        if not text:
            text = ""
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "site_message" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(client=client, title=title, text=text, msg_type="site_message", variables=variables)

    def send_transfer_fail_message(self, path, count, text):
        """
        发送转移失败的消息
        """
        if not path or not count:
            return
        title = f"【{count} 个文件入库失败】"
        text = f"源路径：{path}\n原因：{text}"
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "transfer_fail" in client.get("switchs"):
                variables = {
                    "path": path,
                    "count": count,
                    "text": text,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="unidentification",
                    msg_type="transfer_fail",
                    variables=variables,
                )

    def send_auto_remove_torrents_message(self, title, text):
        """
        发送自动删种的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "auto_remove_torrents" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="torrent_remove",
                    msg_type="auto_remove_torrents",
                    variables=variables,
                )

    def send_brushtask_remove_message(self, title, text):
        """
        发送刷流删种的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "brushtask_remove" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_remove",
                    variables=variables,
                )

    def send_brushtask_added_message(self, title, text):
        """
        发送刷流下种的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "brushtask_added" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_added",
                    variables=variables,
                )

    def send_mediaserver_message(self, event_info: dict, channel, image_url):
        """
        发送媒体服务器的消息
        :param event_info: 事件信息
        :param channel: 服务器类型:
        :param image_url: 图片
        """
        if not event_info or not channel:
            return
        # 拼装消息内容
        _webhook_actions = {
            "library.new": "新入库",
            "system.webhooktest": "测试",
            "playback.start": "开始播放",
            "playback.stop": "停止播放",
            "user.authenticated": "登录成功",
            "user.authenticationfailed": "登录失败",
            "media.play": "开始播放",
            "media.stop": "停止播放",
            "PlaybackStart": "开始播放",
            "PlaybackStop": "停止播放",
            "item.rate": "标记了",
        }
        _webhook_images = {
            "Emby": "https://emby.media/notificationicon.png",
            "Plex": "https://www.plex.tv/wp-content/uploads/2022/04/new-logo-process-lines-gray.png",
            "Jellyfin": "https://play-lh.googleusercontent.com/SCsUK3hCCRqkJbmLDctNYCfehLxsS4ggD1ZPHIFrrAN1Tn9yhjmGMPep2D9lMaaa9eQi",
        }

        if not _webhook_actions.get(event_info.get("event")):
            return

        # 消息标题
        if event_info.get("item_type") in ["TV", "SHOW"]:
            message_title = f"{_webhook_actions.get(event_info.get('event'))}剧集 {event_info.get('item_name')}"
        elif event_info.get("item_type") == "MOV":
            message_title = f"{_webhook_actions.get(event_info.get('event'))}电影 {event_info.get('item_name')}"
        elif event_info.get("item_type") == "AUD":
            message_title = f"{_webhook_actions.get(event_info.get('event'))}有声书 {event_info.get('item_name')}"
        else:
            message_title = f"{_webhook_actions.get(event_info.get('event'))}"

        # 消息内容
        message_texts = []
        if event_info.get("user_name"):
            message_texts.append(f"用户：{event_info.get('user_name')}")
        if event_info.get("device_name"):
            message_texts.append(f"设备：{event_info.get('client')} {event_info.get('device_name')}")
        if event_info.get("ip"):
            message_texts.append(f"位置：{event_info.get('ip')} {WebUtils.get_location(event_info.get('ip'))}")
        if event_info.get("percentage"):
            percentage = round(float(event_info.get("percentage")), 2)
            message_texts.append(f"进度：{percentage}%")
        if event_info.get("overview"):
            message_texts.append(f"剧情：{event_info.get('overview')}")
        message_texts.append(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")

        # 消息图片
        if not image_url:
            image_url = _webhook_images.get(channel)

        # 插入消息中心
        message_content = "\n".join(message_texts)
        self.messagecenter.insert_system_message(title=message_title, content=message_content)

        # 跳转链接
        url = event_info.get("play_url") or ""

        # 发送消息
        for client in self.active_clients:
            if "mediaserver_message" in client.get("switchs"):
                variables = {
                    "event_info": event_info,
                    "channel": channel,
                    "message_title": message_title,
                    "message_content": message_content,
                    "image_url": image_url,
                    "url": url,
                }
                self.__sendmsg(
                    client=client,
                    title=message_title,
                    text=message_content,
                    image=image_url,
                    url=url,
                    msg_type="mediaserver_message",
                    variables=variables,
                )

    def send_plugin_message(self, title, text="", image="", url=""):
        """
        发送插件消息
        """
        if not title:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "custom_message" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                    "url": url,
                    "image": image,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url=url,
                    image=image,
                    msg_type="custom_message",
                    variables=variables,
                )

    def send_custom_message(self, clients, title, text="", image=""):
        """
        发送自定义消息
        """
        if not title:
            return
        if not clients:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if str(client.get("id")) in clients:
                variables = {
                    "title": title,
                    "text": text,
                    "image": image,
                }
                self.__sendmsg(
                    client=client, title=title, text=text, image=image, msg_type="custom_message", variables=variables
                )

    def get_search_types(self):
        """
        获取支持搜索交互的渠道类型（所有消息类渠道）
        """
        return [SearchType.WX, SearchType.TG, SearchType.SLACK, SearchType.SYNOLOGY, SearchType.API, SearchType.PLUGIN]

    def get_message_client_info(self, cid=None):
        """
        获取消息端信息
        """
        self._ensure_loaded()
        if cid:
            return self._client_configs.get(str(cid))
        return self._client_configs

    def get_interactive_client(self, client_type=None):
        """
        查询当前可以交互的渠道
        """
        self._ensure_loaded()
        if client_type:
            return self.active_interactive_clients.get(client_type)
        else:
            return list(self.active_interactive_clients.values())

    def delete_message_client(self, cid):
        """
        删除消息端
        """
        self._ensure_loaded()
        ret = self.config_repo.delete_message_client(cid=cid)
        self._remove_client(cid)
        return ret

    def check_message_client(self, cid=None, interactive=None, enabled=None, ctype=None):
        """
        设置消息端（更新DB后刷新受影响的客户端）
        """
        self._ensure_loaded()
        ret = self.config_repo.check_message_client(cid=cid, interactive=interactive, enabled=enabled, ctype=ctype)
        if cid:
            self._refresh_client(cid)
        if ctype:
            for c in list(self.active_clients):
                if c.get("type") == ctype:
                    self._refresh_client(c.get("id"))
        return ret

    def insert_message_client(self, name, ctype, config, switchs: list, interactive, enabled, note="", templates=None):
        """
        插入消息端
        """
        self._ensure_loaded()
        new_id = self.config_repo.insert_message_client(
            name=name,
            ctype=ctype,
            config=config,
            switchs=switchs,
            interactive=interactive,
            enabled=enabled,
            note=note,
            templates=templates,
        )
        self._refresh_client(new_id)
        return True

    def send_user_statistics_message(self, msgs: list):
        if not msgs:
            return
        title = "站点数据统计"
        text = "\n".join(msgs)
        self.messagecenter.insert_system_message(title=title, content=text)
        for client in self.active_clients:
            if "ptrefresh_date_message" in client.get("switchs"):
                variables = {
                    "msgs": msgs,
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(
                    client=client, title=title, text=text, msg_type="ptrefresh_date_message", variables=variables
                )

    def send_brushtask_pause_message(self, title, text):
        """
        发送刷流暂停种子的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(title=title, content=text)
        # 发送消息
        for client in self.active_clients:
            if "brushtask_pause" in client.get("switchs"):
                variables = {
                    "title": title,
                    "text": text,
                }
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask",
                    msg_type="brushtask_pause",
                    variables=variables,
                )
