"""
数据库模型基础定义
包含 Base 和 BaseMedia 声明式基类
"""

from sqlalchemy.orm import declarative_base

# 使用单一的 Base 来合并两个数据库
Base = declarative_base()
# 为了向后兼容，BaseMedia 也指向同一个 Base
BaseMedia = Base

# MySQL 兼容性说明：
# MySQL 不允许在 TEXT 类型上创建索引，必须使用 String(长度)
# SQLite 和 PostgreSQL 支持 TEXT 索引
