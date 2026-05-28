import contextlib

import log
from app.plugin_framework.hook_system import HookSystem
from app.utils.types import EventType


class EventManager:
    """
    事件管理器（HookSystem 兼容层）
    保留函数级事件注册/监听能力，事件发送同时同步调用本地 handlers 和 HookSystem
    """

    def __init__(self):
        self._handlers = {}

    def add_event_listener(self, etype: EventType, handler):
        try:
            handler_list = self._handlers[etype.value]
        except KeyError:
            handler_list = []
            self._handlers[etype.value] = handler_list
        if handler not in handler_list:
            handler_list.append(handler)
            log.debug(f"已注册事件：{etype.value} {handler}")

    def remove_event_listener(self, etype: EventType, handler):
        try:
            handler_list = self._handlers[etype.value]
            if handler in handler_list[:]:
                handler_list.remove(handler)
            if not handler_list:
                del self._handlers[etype.value]
        except KeyError:
            pass

    def send_event(self, etype: EventType, data: dict | None = None):
        if etype not in EventType:
            return
        event = Event(etype.value)
        event.event_data = data or {}
        log.debug(f"发送事件：{etype.value} - {event.event_data}")

        # 同步调用本地注册的 handlers
        handler_list = self._handlers.get(etype.value, [])
        for handler in handler_list:
            try:
                handler(event)
            except Exception as e:
                log.error(f"事件处理出错：{etype.value} - {e}")

        # 转发到 HookSystem（新插件框架）
        event_map = {
            EventType.CookieSync: "site.cookie_sync",
            EventType.LocalStorageSync: "site.local_storage_sync",
            EventType.TransferFinished: "media.transfered",
            EventType.RefreshMediaServer: "media.library_synced",
            EventType.EmbyWebhook: "webhook.emby",
            EventType.JellyfinWebhook: "webhook.jellyfin",
            EventType.PlexWebhook: "webhook.plex",
            EventType.MediaScrapStart: "media.scraped",
            EventType.SourceFileDeleted: "media.source_deleted",
            EventType.DoubanSync: "media.douban_sync",
            EventType.WeworkLogin: "wework.login",
            EventType.SubtitleDownload: "subtitle.download",
            EventType.MessageIncoming: "message.incoming",
            EventType.SubscribeAdd: "subscribe.add",
            EventType.SubscribeFinished: "subscribe.finished",
            EventType.SearchStart: "search.start",
            EventType.TransferFail: "transfer.fail",
            EventType.LibraryFileDeleted: "library.file_deleted",
            EventType.AutoSeedStart: "autoseed.start",
            EventType.SiteSignin: "site.signin",
            EventType.PluginReload: "plugin.reload",
        }
        if etype in event_map:
            with contextlib.suppress(Exception):
                HookSystem().emit(event_map[etype], data or {})

    def register(self, etype):
        def decorator(f):
            if isinstance(etype, list):
                for et in etype:
                    self.add_event_listener(et, f)
            elif isinstance(etype, type):
                for et in etype.__members__.values():
                    self.add_event_listener(et, f)
            else:
                self.add_event_listener(etype, f)
            return f

        return decorator


class Event:
    def __init__(self, event_type=None):
        self.event_type = event_type
        self.event_data = {}


EventHandler = EventManager()
