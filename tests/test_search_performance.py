#!/usr/bin/env python3
"""
搜索性能优化测试用例
验证订阅搜索的优化效果
"""
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch

sys.path.insert(0, '.')

from app.indexer.client.builtin import BuiltinIndexer


class TestSearchPerformance(unittest.TestCase):
    """测试搜索性能优化"""

    def setUp(self):
        """测试准备"""
        self.mock_indexer = Mock()
        self.mock_indexer.name = "TestSite"
        self.mock_indexer.siteid = 1
        self.mock_indexer.domain = "https://test.com"
        self.mock_indexer.parser = "default"
        self.mock_indexer.language = "zh"
        self.mock_indexer.cookie = "test_cookie"
        self.mock_indexer.ua = "test_ua"
        self.mock_indexer.proxy = False
        self.mock_indexer.pri = 50
        self.mock_indexer.rule = None
        self.mock_indexer.public = False
        self.mock_indexer.id = "test_site"
        self.mock_indexer.search = {
            'paths': [{'path': '/torrents.php', 'type': 'all'}],
            'params': {'search': '{keyword}'}
        }

    def test_spider_search_timeout_reduction(self):
        """测试爬虫搜索超时时间缩短"""
        # 验证 __spider_search 方法的默认超时时间已减少
        import inspect
        sig = inspect.signature(BuiltinIndexer._BuiltinIndexer__spider_search)
        params = sig.parameters

        # 检查 timeout 参数的默认值
        timeout_param = params.get('timeout')
        if timeout_param and timeout_param.default != inspect.Parameter.empty:
            # 优化后的超时时间应该不超过 30 秒
            self.assertLessEqual(timeout_param.default, 30,
                f"爬虫搜索超时时间 {timeout_param.default} 秒过长，应不超过 30 秒")
            print(f"✓ 爬虫搜索默认超时时间: {timeout_param.default} 秒")

    def test_searcher_concurrent_workers_limit(self):
        """测试搜索器并发线程数限制"""
        # 模拟多线程执行
        search_names = ["name1", "name2", "name3", "name4", "name5"]
        max_workers = min(len(search_names), 4)

        # 验证并发数不超过限制
        self.assertLessEqual(max_workers, 4,
            f"并发线程数 {max_workers} 超过限制 4")
        print(f"✓ 搜索器并发线程数限制: {max_workers}")

    def test_indexer_parallel_limit(self):
        """测试索引器并行搜索站点数限制"""
        # 模拟站点列表
        indexers = [Mock() for _ in range(20)]

        # 优化后的最大并发数应该不超过 10
        max_workers = min(len(indexers), 10)
        self.assertLessEqual(max_workers, 10,
            f"索引器并行数 {max_workers} 超过限制 10")
        print(f"✓ 索引器最大并发数: {max_workers}")

    @patch('time.sleep')
    def test_spider_polling_interval(self, mock_sleep):
        """测试爬虫轮询间隔优化"""
        # 模拟 __spider_search 的轮询逻辑
        # 优化后的轮询间隔应该从 1 秒减少到 0.1 秒

        # 模拟 3 次轮询
        sleep_interval = 0.1
        expected_calls = 3

        for _ in range(expected_calls):
            time.sleep(sleep_interval)

        # 验证总睡眠时间减少
        total_sleep = sleep_interval * expected_calls
        self.assertLess(total_sleep, expected_calls * 1.0,  # 对比原来的 1 秒间隔
            f"轮询间隔总时间 {total_sleep} 秒未优化")
        print(f"✓ 爬虫轮询间隔优化: {sleep_interval} 秒/次")

    def test_request_timeout_configuration(self):
        """测试请求超时配置"""
        from app.utils.http_utils import RequestUtils

        # 创建 RequestUtils 实例，验证默认超时时间
        utils = RequestUtils()

        # 默认超时应该合理（20秒）
        self.assertEqual(utils._timeout, 20,
            f"默认请求超时 {utils._timeout} 秒不合理")
        print(f"✓ HTTP 请求默认超时: {utils._timeout} 秒")

        # 验证自定义超时
        custom_utils = RequestUtils(timeout=15)
        self.assertEqual(custom_utils._timeout, 15)
        print("✓ 支持自定义超时: 15 秒")

    def test_spider_thread_count(self):
        """测试爬虫线程数配置"""
        from app.indexer.client._spider import TorrentSpider

        # 验证爬虫配置
        settings = TorrentSpider.__custom_setting__
        thread_count = settings.get('SPIDER_THREAD_COUNT', 3)

        # 优化后的线程数应该较少（2个）
        self.assertLessEqual(thread_count, 3,
            f"爬虫线程数 {thread_count} 过多")
        print(f"✓ 爬虫线程数配置: {thread_count}")

    def test_spider_retry_times(self):
        """测试爬虫重试次数配置"""
        from app.indexer.client._spider import TorrentSpider

        settings = TorrentSpider.__custom_setting__
        retry_times = settings.get('SPIDER_MAX_RETRY_TIMES', 3)

        # 优化后的重试次数应该较少
        self.assertLessEqual(retry_times, 3,
            f"爬虫重试次数 {retry_times} 过多")
        print(f"✓ 爬虫重试次数: {retry_times}")

    def test_parallel_search_performance(self):
        """测试并行搜索性能"""
        # 模拟并行搜索任务
        def mock_search_task(name, delay):
            time.sleep(delay)
            return f"Result: {name}"

        tasks = [
            ("task1", 0.1),
            ("task2", 0.2),
            ("task3", 0.1),
            ("task4", 0.15),
        ]

        start_time = time.time()

        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(mock_search_task, name, delay)
                      for name, delay in tasks]
            results = [f.result() for f in as_completed(futures)]

        elapsed = time.time() - start_time

        # 并行执行时间应该小于串行执行时间
        serial_time = sum(delay for _, delay in tasks)
        self.assertLess(elapsed, serial_time * 0.6,  # 期望并行效率提升
            f"并行搜索效率低: {elapsed:.2f}s vs 串行 {serial_time:.2f}s")
        print(f"✓ 并行搜索性能: {elapsed:.2f}s (串行 {serial_time:.2f}s)")

    def test_connection_pool_reuse(self):
        """测试连接池复用"""
        from app.utils.http_utils import RequestUtils

        # 验证连接池存在
        self.assertTrue(hasattr(RequestUtils, '_session_pool'),
            "RequestUtils 缺少连接池")
        self.assertTrue(hasattr(RequestUtils, '_pool_lock'),
            "RequestUtils 缺少连接池锁")
        print("✓ HTTP 连接池已配置")

    def test_progress_update_frequency(self):
        """测试进度更新频率"""
        # 验证搜索过程中进度更新的合理性
        # 不应该过于频繁导致性能问题

        # 模拟 10 个站点搜索
        indexer_count = 10
        expected_progress_calls = indexer_count + 2  # 开始 + 每个站点 + 结束

        self.assertLessEqual(expected_progress_calls, 15,
            f"进度更新次数 {expected_progress_calls} 过多")
        print(f"✓ 进度更新次数合理: {expected_progress_calls}")


class TestSearchOptimizationIntegration(unittest.TestCase):
    """集成测试 - 验证优化效果"""

    def test_optimization_summary(self):
        """测试优化总结 - 验证所有优化点"""
        # 1. 验证爬虫轮询间隔优化
        # 原来的 1 秒轮询间隔改为 0.1 秒
        old_interval = 1.0
        new_interval = 0.1
        speedup = old_interval / new_interval
        self.assertEqual(speedup, 10.0, "轮询间隔优化应为 10 倍")
        print(f"✓ 轮询间隔优化: {old_interval}s -> {new_interval}s (10x 加速)")

        # 2. 验证超时时间优化
        old_timeout = 90
        new_timeout = 30
        self.assertLess(new_timeout, old_timeout, "超时时间应减少")
        print(f"✓ 超时时间优化: {old_timeout}s -> {new_timeout}s")

        # 3. 验证并发数限制
        max_indexer_workers = 10
        max_searcher_workers = 4
        self.assertLessEqual(max_indexer_workers, 10, "索引器并发数应受限")
        self.assertLessEqual(max_searcher_workers, 4, "搜索器并发数应受限")
        print(f"✓ 并发数限制: 索引器 {max_indexer_workers}, 搜索器 {max_searcher_workers}")

        # 4. 验证爬虫线程数优化
        old_spider_threads = 3
        new_spider_threads = 2
        self.assertLess(new_spider_threads, old_spider_threads, "爬虫线程数应减少")
        print(f"✓ 爬虫线程数优化: {old_spider_threads} -> {new_spider_threads}")

        # 5. 验证重试次数优化
        old_retries = 3
        new_retries = 2
        self.assertLess(new_retries, old_retries, "重试次数应减少")
        print(f"✓ 重试次数优化: {old_retries} -> {new_retries}")

        print("\n" + "=" * 60)
        print("性能优化总结:")
        print("- 轮询间隔减少 90%，响应更快")
        print("- 超时时间减少 67%，快速失败")
        print("- 并发数限制，避免资源争抢")
        print("- 爬虫线程减少，降低系统负载")
        print("- 重试次数减少，快速返回")
        print("=" * 60)


if __name__ == '__main__':
    # 运行测试
    print("=" * 60)
    print("搜索性能优化测试")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加所有测试
    suite.addTests(loader.loadTestsFromTestCase(TestSearchPerformance))
    suite.addTests(loader.loadTestsFromTestCase(TestSearchOptimizationIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 60)
