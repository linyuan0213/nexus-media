"""下载事件队列 — handler put，SSE get."""

import queue

download_event_queue: queue.Queue = queue.Queue()
