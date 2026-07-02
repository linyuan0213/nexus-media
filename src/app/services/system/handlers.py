"""系统领域事件处理器."""

import log
from app.events import Event, on_event
from app.events.constants import LIBRARY_FILE_DELETED, MEDIA_SOURCE_DELETED, MESSAGE_INCOMING
from app.events.payloads import LibraryFileDeletedPayload, MediaSourceDeletedPayload, MessageIncomingPayload


@on_event(MESSAGE_INCOMING)
def handle_message_incoming(event: Event) -> None:
    """消息 incoming 事件处理器"""
    payload = event.payload
    if not isinstance(payload, MessageIncomingPayload):
        payload = MessageIncomingPayload(**payload)
    log.info(f"[Event]消息 incoming: channel={payload.channel} user={payload.user_name}")


@on_event(MEDIA_SOURCE_DELETED)
def handle_media_source_deleted(event: Event) -> None:
    """媒体源文件删除事件处理器"""
    payload = event.payload
    if not isinstance(payload, MediaSourceDeletedPayload):
        payload = MediaSourceDeletedPayload(**payload)
    log.info(f"[Event]源文件删除: {payload.path}/{payload.filename}")


@on_event(LIBRARY_FILE_DELETED)
def handle_library_file_deleted(event: Event) -> None:
    """媒体库文件删除事件处理器"""
    payload = event.payload
    if not isinstance(payload, LibraryFileDeletedPayload):
        payload = LibraryFileDeletedPayload(**payload)
    log.info(f"[Event]库文件删除: {payload.path}/{payload.filename}")
