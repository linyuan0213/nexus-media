from concurrent.futures import ThreadPoolExecutor

_THREAD_NUM = 100
_executor = ThreadPoolExecutor(max_workers=_THREAD_NUM)


class ThreadHelper:
    def start_thread(self, func, kwargs):
        if not _executor:
            return None
        return _executor.submit(func, *kwargs)
