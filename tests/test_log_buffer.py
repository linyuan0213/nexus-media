#!/usr/bin/env python3
"""
测试 LogBuffer 与 LogStreamingService
"""

import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util

_LOG_BUFFER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "utils", "log_buffer.py"
)
_STREAMING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "services", "log_streaming_service.py"
)

spec = importlib.util.spec_from_file_location("log_buffer", _LOG_BUFFER_PATH)
assert spec is not None
log_buffer_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log_buffer_mod)
LogBuffer = log_buffer_mod.LogBuffer

spec2 = importlib.util.spec_from_file_location("log_streaming_service", _STREAMING_PATH)
assert spec2 is not None
streaming_mod = importlib.util.module_from_spec(spec2)
sys.modules["app"] = type(sys)("app")
sys.modules["app.utils"] = type(sys)("app.utils")
sys.modules["app.utils.log_buffer"] = log_buffer_mod
sys.modules["app.services"] = type(sys)("app.services")
spec2.loader.exec_module(streaming_mod)
LogStreamingService = streaming_mod.LogStreamingService


class TestLogBuffer(unittest.TestCase):
    def test_append_and_get_logs(self):
        buf = LogBuffer(maxlen=10)
        buf.append("INFO", "【System】启动服务")
        buf.append("WARN", "【Rss】没有正在订阅的电影")
        buf.append("ERROR", "普通错误信息")

        logs, _ = buf.get_logs()
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["source"], "System")
        self.assertEqual(logs[0]["text"], "启动服务")
        self.assertEqual(logs[1]["source"], "Rss")
        self.assertEqual(logs[1]["level"], "WARN")
        self.assertEqual(logs[2]["source"], "System")

    def test_get_logs_with_source_filter(self):
        buf = LogBuffer(maxlen=10)
        buf.append("INFO", "【System】系统消息")
        buf.append("INFO", "【Rss】RSS消息")
        buf.append("INFO", "【System】另一条系统消息")

        logs, _ = buf.get_logs(source="System")
        self.assertEqual(len(logs), 2)
        self.assertTrue(all(lg["source"] == "System" for lg in logs))

    def test_get_logs_with_last_counter(self):
        buf = LogBuffer(maxlen=10)
        buf.append("INFO", "m1")
        buf.append("INFO", "m2")
        first_counter = buf.counter
        buf.append("INFO", "m3")

        logs, _ = buf.get_logs(last_counter=first_counter)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["text"], "m3")

    def test_maxlen_discard_old(self):
        buf = LogBuffer(maxlen=3)
        buf.append("INFO", "1")
        buf.append("INFO", "2")
        buf.append("INFO", "3")
        buf.append("INFO", "4")

        logs, _ = buf.get_logs()
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["text"], "2")

    def test_escape_html(self):
        buf = LogBuffer(maxlen=10)
        buf.append("INFO", "<script>alert(1)</script>")
        logs, _ = buf.get_logs()
        text = logs[0]["text"]
        self.assertNotIn("<script>", text)
        self.assertIn("script", text)

    def test_thread_safety(self):
        buf = LogBuffer(maxlen=1000)
        errors = []

        def worker():
            try:
                for i in range(100):
                    buf.append("INFO", f"msg-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(errors)
        self.assertEqual(len(buf), 1000)


class TestLogStreamingService(unittest.TestCase):
    def _parse_data(self, data: str):
        return json.loads(data.replace("data: ", "").strip())

    def test_stream_yields_logs(self):
        buf = LogBuffer(maxlen=10)
        service = LogStreamingService(buf, sleep_interval=0.05)

        gen = service.stream(source="")
        data = next(gen)
        self.assertIn("data: []", data)

        buf.append("INFO", "【System】测试日志")
        data = next(gen)
        payload = self._parse_data(data)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["text"], "测试日志")

    def test_stream_source_filter(self):
        buf = LogBuffer(maxlen=10)
        service = LogStreamingService(buf, sleep_interval=0.05)

        gen = service.stream(source="Rss")
        next(gen)

        buf.append("INFO", "【System】系统消息")
        buf.append("INFO", "【Rss】RSS消息")

        data = next(gen)
        payload = self._parse_data(data)
        texts = [lg["text"] for lg in payload]
        self.assertNotIn("系统消息", texts)
        self.assertIn("RSS消息", texts)

    def test_stream_reset_when_buffer_overflow(self):
        buf = LogBuffer(maxlen=3)
        service = LogStreamingService(buf, sleep_interval=0.05)

        gen = service.stream(source="")
        next(gen)

        buf.append("INFO", "a")
        buf.append("INFO", "b")
        buf.append("INFO", "c")
        buf.append("INFO", "d")

        data = next(gen)
        payload = self._parse_data(data)
        texts = [lg["text"] for lg in payload]
        self.assertNotIn("a", texts)
        self.assertIn("d", texts)


if __name__ == "__main__":
    unittest.main()
