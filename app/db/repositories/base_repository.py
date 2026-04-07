"""
Base Repository Class
Provides common database operations and utilities for all repositories.
"""
from app.db import MainDb, DbPersist


class BaseRepository:
    """
    基础仓储类
    提供通用的数据库操作和工具方法
    """
    _db = MainDb()

    def __init__(self):
        """
        初始化仓储
        """
        pass

    @property
    def db(self):
        """
        获取数据库实例
        """
        return self._db

    @classmethod
    def persist(cls, func):
        """
        持久化装饰器
        使用 DbPersist 装饰器包装方法
        """
        return DbPersist(cls._db)(func)

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径格式
        
        Args:
            path: 原始路径
            
        Returns:
            标准化后的路径
        """
        if not path:
            return ""
        import os
        return os.path.normpath(path)

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
        """
        检查查询结果是否存在
        
        Args:
            query: SQLAlchemy 查询对象
            
        Returns:
            是否存在记录
        """
        return query.first() is not None

    def count(self, query) -> int:
        """
        获取查询结果数量
        
        Args:
            query: SQLAlchemy 查询对象
            
        Returns:
            记录数量
        """
        return query.count()
