"""
Base Repository Class
提供显式 session 生命周期管理的通用数据库操作工具方法

设计原则：
- 禁止使用隐式 scoped_session 长期持有连接
- 每个 Repository 方法通过 self.session() 显式获取和释放 session
- 多步骤事务通过 with self.session() as db 在同一 session 内完成
"""

from contextlib import contextmanager

from app.db.session import Database


class BaseRepository:
    """
    基础仓储类

    所有 Repository 通过 self.session() 获取 Session 对象：
    - with self.session() as db:
          db.query(...)
          db.add(...)
          db.commit()

    工具方法（与 session 无关）：
    - _paginate(query, page, rownum)
    - _build_like_pattern(search)
    - exists(query)
    - count(query)
    """

    # 通过 Database 单例统一获取 SessionManager，禁止直接持有 session
    _session_manager = Database().session_manager

    def __init__(self):
        pass

    @contextmanager
    def session(self):
        """获取一个自动提交/回滚/关闭的 session 上下文。"""
        with self._session_manager.session_scope() as session:
            yield session

    @contextmanager
    def readonly(self):
        """只读 session 上下文（不自动提交）。"""
        session = self._session_manager.session()
        try:
            yield session
        finally:
            session.close()
            self._session_manager.remove()

    def _paginate(self, query, page: int, rownum: int):
        """
        分页查询

        Args:
            query: SQLAlchemy 查询对象
            page: 页码（从1开始）
            rownum: 每页行数

        Returns:
            添加了分页限制的查询对象
        """
        begin_pos = 0 if int(page) == 1 else (int(page) - 1) * int(rownum)
        return query.limit(int(rownum)).offset(begin_pos)

    def _build_like_pattern(self, search: str) -> str:
        """
        构建 LIKE 查询模式

        Args:
            search: 搜索关键字

        Returns:
            LIKE 模式字符串
        """
        if not search:
            return "%%"
        return f"%{search}%"

    def exists(self, query) -> bool:
        """检查查询结果是否存在"""
        with self.session() as db:
            return query.with_session(db).first() is not None

    def count(self, query) -> int:
        """获取查询结果数量"""
        with self.session() as db:
            return query.with_session(db).count()
