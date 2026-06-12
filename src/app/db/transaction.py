"""
事务控制模块
提供模块级 transaction_scope 上下文管理器
"""

from contextlib import contextmanager

from app.db.session import get_session_manager


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
