"""MessageDispatcher - 消息队列调度与核心发送."""

from typing import Any

import log
from app.domain.enums import SearchType
from app.infrastructure.queue import MessageQueueFactory
from app.message.web_store import WebMessageStore
from app.utils import StringUtils


class MessageDispatcher:
    """负责消息入队、实际发送和渠道路由."""

    # 绑定表渠道键 → 交互客户端键
    _CHANNEL_KEY_MAP = {
        "telegram": "TG",
        "wechat": "WX",
        "slack": "SLACK",
        "synologychat": "SYNOLOGY",
        "feishu": "FEISHU",
        "dingtalk": "DINGTALK",
    }

    def __init__(self, client_manager, messagecenter, domain: str = ""):
        self._client_manager = client_manager
        self._messagecenter = messagecenter
        self._domain = domain
        self._channel_binding_service = None
        self._queue = MessageQueueFactory.create()
        self._queue.register_handler(self._handle_queued_message)

    def set_channel_binding_service(self, service) -> None:
        """延迟注入渠道绑定服务"""
        self._channel_binding_service = service

    def _handle_queued_message(self, title, text, image, url, user_id, client_id, client_type):
        """队列消息处理器：通过 client_id 找到 client 并发送."""
        client = None
        for c in self._client_manager.active_clients:
            if str(c.get("id")) == client_id:
                client = c
                break
        if client:
            self._do_sendmsg(client, title, text, image, url, user_id)
        else:
            log.warn(f"[Message]队列中找不到客户端: id={client_id}, type={client_type}")

    def _do_sendmsg(self, client, title, text, image, url, user_id):
        """实际执行消息发送（由队列调用）."""
        if not client or not client.get("client"):
            log.warn("[Message]客户端对象为空，跳过发送")
            return
        cname = client.get("name")
        log.info(f"[Message]开始发送消息 {cname}：title={title}")
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
                log.error(f"[Message]{cname} 消息发送失败：%s" % ret_msg)
                raise RuntimeError(ret_msg)
        log.info(f"[Message]消息发送成功 {cname}：title={title}")

    def sendmsg(
        self,
        client,
        title,
        text: str | None = None,
        image: str | None = None,
        url: str | None = None,
        user_id: str = "",
        msg_type: str | None = None,
        variables: dict | None = None,
        template_engine=None,
    ):
        """通用消息发送（异步入队）."""
        if not client or not client.get("client"):
            return False
        if msg_type and variables and template_engine:
            template_title, template_text = template_engine.apply_client_template(client, msg_type, variables)
            title = template_title if template_title is not None else title
            text = template_text if template_text else text
        cname = client.get("name")
        log.info(f"[Message]消息入队 {cname}：title={title}")
        if not self._queue:
            return False
        return self._queue.submit(self._do_sendmsg, client, title, text, image, url, user_id, name=f"sendmsg:{cname}")

    def send_channel_msg(
        self,
        channel: Any,
        title: str,
        text: str = "",
        image: str | None = None,
        url: str | None = None,
        user_id: str = "",
    ) -> bool:
        """按渠道发送消息，用于消息交互."""
        if channel == SearchType.WEB:
            if self._messagecenter:
                self._messagecenter.insert_system_message(title=title, content=text)
            WebMessageStore.instance().add(
                title=title, content=text, kind="reply", image=image or "", url=url or "", user_id=user_id
            )
            return True
        client = self._client_manager.get_interactive_client(channel)
        if client:
            return self.sendmsg(client=client, title=title, text=text, image=image, url=url, user_id=user_id)
        return False

    def send_user_msg(
        self,
        system_user_id: int | None,
        title: str,
        text: str = "",
        image: str | None = None,
        url: str | None = None,
    ) -> bool:
        """按归属用户定向发送（ADR-021 5.6）：Web 消息 + 该用户绑定的外部渠道."""
        delivered = False
        self.send_channel_msg(SearchType.WEB, title, text, image=image, url=url, user_id=str(system_user_id or ""))
        delivered = True
        if system_user_id and self._channel_binding_service is not None:
            for binding in self._channel_binding_service.list_bindings(system_user_id):
                client_key = self._CHANNEL_KEY_MAP.get(binding.get("channel", ""))
                if not client_key:
                    continue
                client = self._client_manager.get_interactive_client(client_key)
                if client:
                    try:
                        self.sendmsg(
                            client=client,
                            title=title,
                            text=text,
                            image=image,
                            url=url,
                            user_id=binding.get("channel_user_id", ""),
                        )
                        delivered = True
                    except Exception:  # noqa: BLE001
                        log.debug(f"[Message]定向发送失败: channel={binding.get('channel')}")
        return delivered

    def _do_send_list_msg(self, client, medias, user_id, title):
        """实际执行列表消息发送（由队列调用）."""
        if not client or not client.get("client"):
            log.warn("[Message]客户端对象为空，跳过列表发送")
            return
        cname = client.get("name")
        log.info(f"[Message]开始发送列表消息 {cname}：title={title}")
        state, ret_msg = client.get("client").send_list_msg(
            medias=medias, user_id=user_id, title=title, url=self._domain
        )
        if not state:
            log.error(f"[Message]{cname} 发送列表消息失败：%s" % ret_msg)
            raise RuntimeError(ret_msg)
        log.info(f"[Message]列表消息发送成功 {cname}：title={title}")

    def send_list_msg(self, client, medias, user_id, title):
        """发送选择类消息（异步入队）."""
        if not client or not client.get("client"):
            return False
        cname = client.get("name")
        log.info(f"[Message]列表消息入队 {cname}：title={title}")
        if not self._queue:
            return False
        return self._queue.submit(self._do_send_list_msg, client, medias, user_id, title, name=f"send_list_msg:{cname}")

    def send_channel_list_msg(self, channel: Any, title: str, medias: list, user_id: str = "") -> bool:
        """发送列表选择消息，用于消息交互."""
        if channel == SearchType.WEB:
            items = WebMessageStore.build_list_items(medias)
            content = "\n".join(f"{it['index']}. {it['title']}，{it['vote']}".strip() for it in items)
            if self._messagecenter:
                self._messagecenter.insert_system_message(title=title, content=content)
            WebMessageStore.instance().add(title=title, content="", kind="list", items=items, user_id=user_id)
            return True
        client = self._client_manager.get_interactive_client(channel)
        if client:
            return self.send_list_msg(client=client, title=title, medias=medias, user_id=user_id)
        return False

    def get_search_types(self) -> list:
        """获取支持搜索交互的渠道标识：已启用交互渠道动态推导 + 系统保留标识.

        直接读内存缓存（不触发 _ensure_loaded 的全量 DB 查询），
        保留内置交互渠道标识以避免存量渠道行为回归。
        """
        types = list(self._client_manager._active_interactive_clients.keys())  # noqa: SLF001
        for builtin in ("WX", "TG", "SLACK", "SYNOLOGY", "API", "PLUGIN"):
            if builtin not in types:
                types.append(builtin)
        return types
