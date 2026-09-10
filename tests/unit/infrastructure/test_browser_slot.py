"""浏览器并发闸门测试：占满时等待，释放后放行."""

import threading
import time
from unittest.mock import patch

from app.infrastructure.chrome import limits


def test_full_slot_waits_until_release():
    sem = threading.BoundedSemaphore(1)
    with patch.object(limits, "_browser_semaphore", sem):
        first = limits.browser_slot()
        first.__enter__()  # 占满
        acquired: list[float] = []

        def worker():
            with limits.browser_slot():
                acquired.append(time.monotonic())

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.3)
        assert acquired == []  # 已满 → 等待
        first.__exit__(None, None, None)
        t.join(timeout=2)
        assert len(acquired) == 1  # 释放后放行
