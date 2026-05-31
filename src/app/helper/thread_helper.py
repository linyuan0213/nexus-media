from concurrent.futures import ThreadPoolExecutor

from app.db.session import remove_session

_THREAD_NUM = 100
_executor = ThreadPoolExecutor(max_workers=_THREAD_NUM)


class ThreadHelper:
    def start_thread(self, func, kwargs):
        if not _executor:
            return None

        def _wrapper(*args, **inner_kwargs):
            try:
                return func(*args, **inner_kwargs)
            finally:
                remove_session()

        return _executor.submit(_wrapper, *kwargs)
