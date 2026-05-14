#!/usr/bin/env python3
"""
测试请求去重器修复
"""

import threading
import time
import unittest

from app.utils.request_deduper import RequestDeduper


class TestRequestDeduper(unittest.TestCase):
    def test_concurrent_dedup(self):
        """测试并发请求去重能正确共享结果"""
        deduper = RequestDeduper(default_timeout=5.0)
        results = []
        lock = threading.Lock()
        call_count = [0]

        def slow_func():
            time.sleep(0.3)
            with lock:
                call_count[0] += 1
            return "ok"

        def worker():
            ret = deduper.execute("key1", slow_func)
            with lock:
                results.append(ret)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(call_count[0], 1, "慢函数应该只被调用一次")
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r == "ok" for r in results), "所有线程都应拿到结果")

    def test_timeout(self):
        """测试超时情况"""
        deduper = RequestDeduper(default_timeout=0.1)

        def slow_func():
            time.sleep(1)
            return "ok"

        # 第一个线程执行慢函数
        t1 = threading.Thread(target=lambda: deduper.execute("key2", slow_func))
        t1.start()
        time.sleep(0.05)

        # 第二个线程等待，应该超时
        with self.assertRaises(TimeoutError):
            deduper.execute("key2", slow_func)

        t1.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
