#!/usr/bin/env python3
"""
测试重构后的日志模块 (log / log.py)

验证点：
1. 向后兼容的 import 方式（import log）
2. 日志级别函数（debug / info / warn / error / console）
3. LOG_BUFFER / LOG_QUEUE 代理行为
4. Logger 单例管理
5. InterceptHandler 存在性
"""

import logging
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试顶层 import log 的兼容方式
import log

# 同时测试新包导入
from log import (
    LOG_BUFFER,
    InterceptHandler,
    Logger,
    console,
    debug,
    error,
    get_log_buffer,
    get_logger_instance,
    info,
    warn,
)


class TestBackwardCompatibility(unittest.TestCase):
    """验证旧的 import 方式仍然可用。"""

    def test_import_log_has_functions(self):
        self.assertTrue(hasattr(log, "debug"))
        self.assertTrue(hasattr(log, "info"))
        self.assertTrue(hasattr(log, "warn"))
        self.assertTrue(hasattr(log, "error"))
        self.assertTrue(hasattr(log, "console"))

    def test_import_log_has_buffer(self):
        self.assertTrue(hasattr(log, "LOG_BUFFER"))
        self.assertTrue(hasattr(log, "LOG_QUEUE"))

    def test_log_queue_same_as_buffer(self):
        self.assertIs(log.LOG_QUEUE, log.LOG_BUFFER)


class TestLogBufferProxy(unittest.TestCase):
    """测试 LogBufferProxy 延迟加载与基本行为。"""

    def setUp(self):
        # 每次测试前清空底层 buffer
        buf = get_log_buffer()
        with buf._lock:
            buf._queue.clear()
            buf._counter = 0

    def test_append_and_length(self):
        LOG_BUFFER.append("INFO", "test1")
        LOG_BUFFER.append("DEBUG", "test2")
        self.assertEqual(len(LOG_BUFFER), 2)

    def test_get_logs_basic(self):
        LOG_BUFFER.append("INFO", "【System】hello")
        LOG_BUFFER.append("WARN", "【Rss】world")
        logs, counter = LOG_BUFFER.get_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["source"], "System")
        self.assertEqual(logs[1]["source"], "Rss")
        self.assertEqual(counter, 2)

    def test_get_logs_with_source(self):
        LOG_BUFFER.append("INFO", "【System】sys")
        LOG_BUFFER.append("INFO", "【Rss】rss")
        logs, _ = LOG_BUFFER.get_logs(source="Rss")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["source"], "Rss")

    def test_proxy_counter(self):
        LOG_BUFFER.append("INFO", "a")
        LOG_BUFFER.append("INFO", "b")
        self.assertEqual(LOG_BUFFER.counter, 2)

    def test_proxy_iteration(self):
        LOG_BUFFER.append("INFO", "x")
        items = list(LOG_BUFFER)
        self.assertEqual(len(items), 1)

    def test_proxy_getitem(self):
        LOG_BUFFER.append("INFO", "m")
        item = LOG_BUFFER[0]
        self.assertEqual(item["text"], "m")


class TestLoggerManager(unittest.TestCase):
    """测试 Logger 单例与实例管理。"""

    def test_singleton_same_module(self):
        logger1 = Logger.get_instance("test_mod")
        logger2 = Logger.get_instance("test_mod")
        self.assertIs(logger1, logger2)

    def test_different_module_different_instance(self):
        logger_a = Logger.get_instance("mod_a")
        logger_b = Logger.get_instance("mod_b")
        # Logger 类按模块缓存，但内部使用同一个 loguru.logger
        self.assertIsInstance(logger_a, Logger)
        self.assertIsInstance(logger_b, Logger)

    def test_get_logger_instance_helper(self):
        self.assertIs(get_logger_instance("x"), Logger.get_instance("x"))

    def test_logger_has_log_attr(self):
        from loguru import logger as _logger

        lg = Logger.get_instance("any")
        self.assertIs(lg.log, _logger)


class TestInterceptHandler(unittest.TestCase):
    """测试 InterceptHandler 可用性。"""

    def test_handler_exists(self):
        self.assertTrue(callable(InterceptHandler))

    def test_handler_emit(self):
        handler = InterceptHandler()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        # 应正常执行不抛出异常
        handler.emit(record)


class TestLoggingFunctions(unittest.TestCase):
    """测试日志 API 函数调用不报错。"""

    def test_debug_does_not_raise(self):
        try:
            debug("debug test", module="test")
        except Exception as e:
            self.fail(f"debug() raised {e}")

    def test_info_does_not_raise(self):
        try:
            info("info test", module="test")
        except Exception as e:
            self.fail(f"info() raised {e}")

    def test_warn_does_not_raise(self):
        try:
            warn("warn test", module="test")
        except Exception as e:
            self.fail(f"warn() raised {e}")

    def test_error_does_not_raise(self):
        try:
            error("error test", module="test")
        except Exception as e:
            self.fail(f"error() raised {e}")

    def test_console_does_not_raise(self):
        try:
            console("console test")
        except Exception as e:
            self.fail(f"console() raised {e}")


class TestThreadSafety(unittest.TestCase):
    """验证 Logger 实例获取在多线程下安全。"""

    def test_concurrent_get_instance(self):
        results = []
        errors = []

        def worker():
            try:
                lg = Logger.get_instance("thread_test")
                results.append(id(lg))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(errors)
        # 所有线程获取的实例 id 应相同
        self.assertEqual(len(set(results)), 1)


if __name__ == "__main__":
    unittest.main()
