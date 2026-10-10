"""数据库连接池泄漏回归：事务 Session 不得跨线程复用。

`ThreadExecutor.submit` 使用 `contextvars.copy_context()` 传递调度连接池覆盖，
会连带复制 `db_tx_session`（事务共享 Session）。若子线程复用它，
`session_scope()` 命中共享 Session 会直接返回而不 commit/close，导致连接永不归还。
"""

import contextvars
import threading

from app.db.session import get_session_manager


def test_tx_session_not_reused_across_threads():
    mgr = get_session_manager()
    captured: dict = {}

    with mgr.transaction_scope() as parent:
        # 同线程内应复用共享 Session
        assert mgr.current_tx_session() is parent

        def child():
            captured["shared"] = mgr.current_tx_session()
            with mgr.session_scope() as s:
                captured["child"] = s

        ctx = contextvars.copy_context()
        t = threading.Thread(target=lambda: ctx.run(child))
        t.start()
        t.join()

    assert captured["shared"] is None
    assert captured["child"] is not parent
