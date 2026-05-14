"""
线程优化测试用例
测试多线程竞争优化后的性能和正确性
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

import pytest


class TestLockOptimization:
    """测试锁优化"""

    def test_rlock_vs_lock_performance(self):
        """测试RLock与普通Lock的性能差异"""
        # 普通Lock
        normal_lock = threading.Lock()
        normal_counter = 0

        # RLock
        rlock = threading.RLock()
        rlock_counter = 0

        def increment_with_lock(lock, counter_ref, iterations):
            for _ in range(iterations):
                with lock:
                    counter_ref[0] += 1

        # 测试普通Lock
        normal_counter = [0]
        threads = []
        start = time.time()
        for _ in range(10):
            t = threading.Thread(target=increment_with_lock, args=(normal_lock, normal_counter, 100))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        normal_time = time.time() - start

        # 测试RLock
        rlock_counter = [0]
        threads = []
        start = time.time()
        for _ in range(10):
            t = threading.Thread(target=increment_with_lock, args=(rlock, rlock_counter, 100))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rlock_time = time.time() - start

        # 两者都应该正确计数
        assert normal_counter[0] == 1000
        assert rlock_counter[0] == 1000

        # 记录性能差异（RLock应该略有开销但更安全）
        print(f"\n普通Lock耗时: {normal_time:.4f}秒")
        print(f"RLock耗时: {rlock_time:.4f}秒")

    def test_double_check_locking_pattern(self):
        """测试双重检查锁定模式的正确性"""
        _instance = None
        _lock = threading.Lock()
        results = []

        def get_instance():
            nonlocal _instance
            # 第一次检查（无锁）
            if _instance is not None:
                return _instance
            # 获取锁
            with _lock:
                # 第二次检查（有锁）
                if _instance is None:
                    _instance = object()
                return _instance

        threads = []
        for _ in range(50):
            t = threading.Thread(target=lambda: results.append(id(get_instance())))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有结果应该是同一个对象
        assert len(set(results)) == 1


class TestThreadPoolOptimization:
    """测试线程池优化"""

    def test_thread_pool_context_manager(self):
        """测试线程池上下文管理器"""

        @contextmanager
        def optimized_executor(max_workers):
            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                yield executor
            finally:
                executor.shutdown(wait=False)

        results = []

        # 使用上下文管理器
        with optimized_executor(4) as executor:
            futures = [executor.submit(lambda x: x * x, i) for i in range(10)]
            for future in as_completed(futures):
                results.append(future.result())

        assert sorted(results) == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

    def test_thread_pool_vs_sequential(self):
        """测试线程池并发 vs 串行性能"""

        def slow_task(n):
            time.sleep(0.01)
            return n * n

        # 串行执行
        start = time.time()
        sequential_results = [slow_task(i) for i in range(8)]
        sequential_time = time.time() - start

        # 线程池并发执行
        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(slow_task, i) for i in range(8)]
            parallel_results = [f.result() for f in futures]
        parallel_time = time.time() - start

        # 结果应该相同
        assert sorted(sequential_results) == sorted(parallel_results)

        # 并发应该更快
        print(f"\n串行耗时: {sequential_time:.4f}秒")
        print(f"并发耗时: {parallel_time:.4f}秒")
        print(f"加速比: {sequential_time / parallel_time:.2f}x")

        assert parallel_time < sequential_time * 0.5

    def test_graceful_shutdown(self):
        """测试线程池优雅关闭"""
        executor = ThreadPoolExecutor(max_workers=2)

        # 提交任务
        futures = [executor.submit(lambda: time.sleep(0.1) or 42) for _ in range(4)]

        # 立即关闭（不等待）
        executor.shutdown(wait=False)

        # 等待已提交的任务完成
        completed = 0
        for f in futures:
            try:
                f.result(timeout=1.0)
                completed += 1
            except:
                pass

        # 大部分任务应该已完成
        assert completed >= 2


class TestConcurrencySafety:
    """测试并发安全性"""

    def test_shared_list_thread_safety(self):
        """测试共享列表的线程安全"""
        shared_list = []
        list_lock = threading.Lock()
        errors = []

        def append_items(thread_id, count):
            try:
                for i in range(count):
                    with list_lock:
                        shared_list.append(f"thread_{thread_id}_item_{i}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=append_items, args=(i, 20))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(shared_list) == 100

    def test_dict_concurrent_access(self):
        """测试字典并发访问"""
        shared_dict = {}
        dict_lock = threading.Lock()
        errors = []

        def update_dict(thread_id):
            try:
                for i in range(10):
                    with dict_lock:
                        key = f"key_{i}"
                        if key in shared_dict:
                            shared_dict[key].append(thread_id)
                        else:
                            shared_dict[key] = [thread_id]
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=update_dict, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # 每个key应该有5个值（5个线程）
        for key in shared_dict:
            assert len(shared_dict[key]) == 5

    def test_fine_grained_locks(self):
        """测试细粒度锁的性能优势"""
        # 全局锁
        global_lock = threading.Lock()
        global_data = []

        # 细粒度锁
        lock_a = threading.Lock()
        lock_b = threading.Lock()
        data_a = []
        data_b = []

        def work_with_global_lock():
            for _ in range(50):
                with global_lock:
                    global_data.append(1)
                    time.sleep(0.001)

        def work_with_fine_grained(thread_id):
            for _ in range(50):
                if thread_id % 2 == 0:
                    with lock_a:
                        data_a.append(1)
                        time.sleep(0.001)
                else:
                    with lock_b:
                        data_b.append(1)
                        time.sleep(0.001)

        # 测试全局锁
        threads = []
        start = time.time()
        for _ in range(4):
            t = threading.Thread(target=work_with_global_lock)
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        global_time = time.time() - start

        # 测试细粒度锁
        threads = []
        start = time.time()
        for i in range(4):
            t = threading.Thread(target=work_with_fine_grained, args=(i,))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        fine_time = time.time() - start

        assert len(global_data) == 200
        assert len(data_a) == 100
        assert len(data_b) == 100

        print(f"\n全局锁耗时: {global_time:.4f}秒")
        print(f"细粒度锁耗时: {fine_time:.4f}秒")
        print(f"性能提升: {global_time / fine_time:.2f}x")


class TestRealWorldScenarios:
    """测试真实场景"""

    def test_download_deduplication_lock(self):
        """模拟下载去重锁的场景"""
        download_locks = {}
        locks_lock = threading.Lock()
        download_results = {}  # 存储下载结果
        threading.Lock()

        def download_image(url):
            cache_key = url.split("/")[-1]

            # 获取或创建锁
            with locks_lock:
                if cache_key not in download_locks:
                    download_locks[cache_key] = threading.Lock()
                lock = download_locks[cache_key]

            # 使用锁防止重复下载
            with lock:
                # 检查是否已经下载过
                if cache_key in download_results:
                    return download_results[cache_key]

                # 模拟下载
                time.sleep(0.01)
                result = f"content_{cache_key}"
                download_results[cache_key] = result
                return result

        # 模拟多个线程同时请求同一个URL
        urls = ["http://example.com/img1.jpg"] * 5 + ["http://example.com/img2.jpg"] * 5

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(download_image, urls))

        # 虽然请求了10次，但只下载了2个不同的图片
        assert len(download_results) == 2, f"应该只下载2个不同图片，实际下载{len(download_results)}个"
        assert len(results) == 10
        # 所有结果应该相同（复用缓存）
        assert results.count("content_img1.jpg") == 5
        assert results.count("content_img2.jpg") == 5

    def test_session_pool_concurrent_access(self):
        """模拟session池并发访问"""
        session_pool = {}
        pool_lock = threading.Lock()
        session_count = [0]

        def get_session(domain):
            with pool_lock:
                if domain not in session_pool:
                    session_pool[domain] = f"session_{domain}"
                    session_count[0] += 1
                return session_pool[domain]

        domains = ["api1.com", "api2.com", "api1.com", "api3.com", "api2.com"] * 10

        with ThreadPoolExecutor(max_workers=5) as executor:
            sessions = list(executor.map(get_session, domains))

        # 应该只创建了3个session
        assert session_count[0] == 3
        assert len(set(sessions)) == 3

    def test_rate_limiter_with_lock(self):
        """模拟带锁的速率限制器"""
        tokens = 5
        max_tokens = 5
        last_update = time.time()
        rate = 2.0  # 每秒2个令牌
        lock = threading.Lock()

        def acquire_token():
            nonlocal tokens, last_update
            with lock:
                now = time.time()
                elapsed = now - last_update
                tokens = min(max_tokens, tokens + elapsed * rate)
                last_update = now

                if tokens >= 1:
                    tokens -= 1
                    return True
                return False

        # 快速获取令牌
        results = []
        for _ in range(10):
            results.append(acquire_token())

        # 前5个应该成功，后面的应该失败
        assert results[:5].count(True) == 5

        # 等待补充令牌
        time.sleep(1.0)

        # 应该可以获取更多令牌
        new_results = [acquire_token() for _ in range(3)]
        assert new_results.count(True) >= 2  # 至少补充了2个


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
