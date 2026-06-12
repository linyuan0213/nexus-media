"""
Redis Stream 消息队列 — 可靠投递，支持 ACK 和幂等去重
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import log
from app.db.session import remove_session
from app.infrastructure.queue.base import MessageQueue
from app.infrastructure.redis import RedisStore

STREAM_KEY = "nexus_media:message_queue"
CONSUMER_GROUP = "message_consumers"
DEDUP_KEY = "nexus_media:message_dedup"
DEDUP_TTL = 86400  # 24小时


class RedisMessageQueue(MessageQueue):
    """Redis Stream 消息队列（可靠投递，进程重启不丢失）"""

    def __init__(self, max_workers: int = 5):
        self._redis = RedisStore()
        self._available = self._redis.is_available()
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="RedisMQ")
        self._shutdown = False
        self._dispatcher: threading.Thread | None = None
        self._handler: Callable | None = None

        if self._available:
            self._init_stream()
            self._start_dispatcher()
            log.info("[RedisMessageQueue]Redis Stream 队列已启动")

    def _init_stream(self):
        """初始化 Stream 和消费者组"""
        try:
            import redis

            client = self._redis._client
            if client:
                try:
                    client.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
                except redis.ResponseError as e:
                    if "already exists" not in str(e):
                        raise
        except Exception as e:
            log.error(f"[RedisMessageQueue]初始化 Stream 失败: {e}")
            self._available = False

    def _start_dispatcher(self):
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True, name="RedisMQDispatcher")
        self._dispatcher.start()

    def start(self) -> None:
        if not self._started:
            self._start_dispatcher()

    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        self._shutdown = True
        if self._dispatcher and self._dispatcher.is_alive():
            self._dispatcher.join(timeout=timeout)
        self._executor.shutdown(wait=wait)
        log.info("[RedisMessageQueue]队列已停止")

    def register_handler(self, handler: Callable) -> None:
        """注册消息处理器，处理器接收 (title, text, image, url, user_id, client_id, client_type)"""
        self._handler = handler

    def submit(self, func: Callable, *args, name: str = "", **kwargs) -> bool:
        """提交消息到 Redis Stream
        从 args/kwargs 中提取可序列化的消息内容
        """
        if not self._available:
            return False

        # 从 args 中提取参数（Message.__sendmsg 的调用方式）
        # args = (client, title, text, image, url, user_id)
        client = args[0] if len(args) > 0 else {}
        title = args[1] if len(args) > 1 else ""
        text = args[2] if len(args) > 2 else ""
        image = args[3] if len(args) > 3 else ""
        url = args[4] if len(args) > 4 else ""
        user_id = args[5] if len(args) > 5 else ""

        msg_id = str(uuid.uuid4())
        payload = {
            "msg_id": msg_id,
            "name": name,
            "timestamp": time.time(),
            "client_id": str(client.get("id", "")) if client else "",
            "client_type": str(client.get("type", "")) if client else "",
            "title": str(title) if title is not None else "",
            "text": str(text) if text is not None else "",
            "image": str(image) if image is not None else "",
            "url": str(url) if url is not None else "",
            "user_id": str(user_id) if user_id is not None else "",
        }

        # 幂等检查
        if self._redis.exists(f"{DEDUP_KEY}:{msg_id}"):
            return True

        stream_id = self._redis.xadd(STREAM_KEY, payload, max_len=10000)
        if stream_id:
            self._redis.set(f"{DEDUP_KEY}:{msg_id}", "1", ex=DEDUP_TTL)
            log.info(f"[RedisMessageQueue]消息已入队: {name} (id={stream_id})")
            return True
        return False

    def is_available(self) -> bool:
        return self._available

    @property
    def pending(self) -> int:
        if not self._available:
            return 0
        return self._redis.xpending(STREAM_KEY, CONSUMER_GROUP)

    def _dispatch_loop(self):
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        while not self._shutdown:
            try:
                messages = self._redis.xreadgroup(CONSUMER_GROUP, consumer_id, {STREAM_KEY: ">"}, count=1, block=3000)
                if not messages:
                    continue
                for _stream_name, entries in messages:
                    for msg_id, fields in entries:
                        fields = {
                            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                            for k, v in fields.items()
                        }
                        self._executor.submit(self._process_message, msg_id, fields)
            except TimeoutError as e:
                log.debug(f"[RedisMessageQueue]xreadgroup 超时，将重试: {e}")
                time.sleep(1)
            except Exception as e:
                log.error(f"[RedisMessageQueue]分发异常: {e}")
                time.sleep(1)

    def _process_message(self, msg_id: str, fields: dict):
        try:
            name = fields.get("name", "")
            client_id = fields.get("client_id", "")
            client_type = fields.get("client_type", "")
            title = fields.get("title", "")
            text = fields.get("text", "")
            image = fields.get("image", "")
            url = fields.get("url", "")
            user_id = fields.get("user_id", "")

            if self._handler:
                self._handler(title, text, image, url, user_id, client_id, client_type)

            self._redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
            log.info(f"[RedisMessageQueue]消息处理成功: {name}")
        except Exception as e:
            log.error(f"[RedisMessageQueue]消息处理失败: {e}")
            # 不 ACK，保留在 Pending 列表中自动重试
        finally:
            remove_session()

    @property
    def _started(self):
        return self._dispatcher is not None and self._dispatcher.is_alive()
