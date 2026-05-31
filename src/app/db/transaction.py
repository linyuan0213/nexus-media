"""
事务控制模块
提供 auto_commit 装饰器和 transaction_scope 上下文管理器
"""

from contextlib import contextmanager

from app.db.session import get_session_manager
from app.utils import ExceptionUtils


class auto_commit:
    """
    自动持久化装饰器 - 自动重试的 commit/rollback

    事务感知：当外部存在显式事务（SessionManager.in_transaction=True）时，
    跳过内部 commit/rollback，由外层事务统一管理。

    重要变更：不再关闭 session（scoped_session 同线程共享，
    由请求级别 remove_session() 统一清理）
    """

    def __init__(self, db=None, max_retries=3, retry_delay=0.1):
        self.db = db
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def __call__(self, f):
        def persist(*args, **kwargs):
            in_tx = False
            if self.db and hasattr(self.db, "in_transaction"):
                in_tx = self.db.in_transaction

            for attempt in range(self.max_retries):
                try:
                    ret = f(*args, **kwargs)
                    if self.db and not in_tx:
                        self.db.commit()
                    return ret if ret is not None else True
                except Exception as e:
                    if self.db and not in_tx:
                        self.db.rollback()
                    if attempt < self.max_retries - 1:
                        import time

                        time.sleep(self.retry_delay * (attempt + 1))
                    else:
                        ExceptionUtils.exception_traceback(e)
                        return False
                finally:
                    if self.db and not in_tx:
                        try:
                            self.db.session.close()
                        except Exception:
                            pass
                        self.db.remove()
            return False

        return persist


@contextmanager
def transaction_scope():
    """
    模块级显式事务上下文管理器

    使用模式：
        from app.db.transaction import transaction_scope
        with transaction_scope():
            repo1.update(...)
            repo2.insert(...)
    """
    manager = get_session_manager()
    with manager.transaction_scope():
        yield
