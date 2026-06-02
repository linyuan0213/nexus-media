"""搜索领域事件处理器."""

import log
from app.events import Event, on_event
from app.events.constants import SEARCH_START
from app.events.payloads import SearchStartPayload


@on_event(SEARCH_START)
def handle_search_start(event: Event) -> None:
    """搜索开始事件处理器"""
    payload = SearchStartPayload(**event.payload)
    log.info(f"[Event]搜索开始: {payload.key_word} 类型: {payload.search_type}")
