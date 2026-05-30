"""
Base Repository Class
提供通用的数据库操作和工具方法，所有 Repository 继承此类

改进：
- _db 改为 SessionManager 实例，提供 session_scope() 上下文管理器
- 保持 query/insert/commit/delete/flush/rollback/execute 兼容方法
- 新增 transactional() 上下文管理器供新代码使用
"""

from contextlib import contextmanager

from app.db.session import Database


class BaseRepository:
    """
    基础仓储类

    所有 Repository 通过 self._db / self.db 访问 SessionManager 方法：
    - query(*entities)     → 创建查询
    - insert(data)         → 插入对象（不自动 commit）
    - delete(obj)          → 删除对象（不自动 commit）
    - commit()             → 提交事务
    - rollback()           → 回滚事务
    - flush()              → 刷写 session
    - execute(sql)         → 执行 SQL
    - bulk_insert(...)     → 批量插入 ORM 对象
    - bulk_insert_mappings(...) → 批量插入字典映射
    - session_scope()      → 事务上下文管理器（推荐新代码使用）
    """

    # 通过 Database 单例统一获取 SessionManager，避免独立实例和导入时副作用
    _db = Database().session_manager

    def __init__(self):
        pass

    @property
    def db(self):
        """推荐访问方式"""
        return self._db

    @contextmanager
    def transactional(self):
        """
        事务上下文管理器（推荐新代码使用）

        使用示例：
            with self.transactional() as session:
                session.add(obj)
                # 自动 commit，异常自动 rollback
        """
        with self._db.session_scope() as session:
            yield session

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
        return query.first() is not None

    def count(self, query) -> int:
        """获取查询结果数量"""
        return query.count()
