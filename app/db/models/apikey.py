# coding: utf-8
"""
API Key 管理模型
包含: API Key 表和使用记录表
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index

from app.db.models.base import Base


class APIKEY(Base):
    """
    API Key 表
    存储用户生成的 API Key 信息
    """
    __tablename__ = 'API_KEYS'

    ID = Column(Integer, primary_key=True)
    # API Key 名称
    NAME = Column(String(255), nullable=False)
    # API Key 值 (前缀 + 哈希或加密后的值)
    KEY_VALUE = Column(String(255), nullable=False, unique=True, index=True)
    # API Key 前缀 (用于显示，如 nk_xxxx)
    KEY_PREFIX = Column(String(20), nullable=False)
    # 状态: 1=启用, 0=禁用
    STATUS = Column(Integer, default=1, nullable=False)
    # 过期时间
    EXPIRES_AT = Column(DateTime, nullable=True)
    # 创建时间
    CREATED_AT = Column(DateTime, default=datetime.now, nullable=False)
    # 更新时间
    UPDATED_AT = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    # 创建人用户ID
    CREATED_BY = Column(Integer, nullable=True)
    # 使用次数统计
    USE_COUNT = Column(Integer, default=0, nullable=False)
    # 最后使用时间
    LAST_USED_AT = Column(DateTime, nullable=True)
    # 描述/备注
    DESCRIPTION = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_API_KEYS_STATUS', 'STATUS'),
        Index('ix_API_KEYS_CREATED_AT', 'CREATED_AT'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.ID,
            'name': self.NAME,
            'key_value': self.KEY_VALUE,
            'key_prefix': self.KEY_PREFIX,
            'status': self.STATUS,
            'expires_at': self.EXPIRES_AT.isoformat() if self.EXPIRES_AT else None,
            'created_at': self.CREATED_AT.isoformat() if self.CREATED_AT else None,
            'updated_at': self.UPDATED_AT.isoformat() if self.UPDATED_AT else None,
            'created_by': self.CREATED_BY,
            'use_count': self.USE_COUNT,
            'last_used_at': self.LAST_USED_AT.isoformat() if self.LAST_USED_AT else None,
            'description': self.DESCRIPTION,
        }

    def is_expired(self):
        """检查是否已过期"""
        if self.EXPIRES_AT is None:
            return False
        return datetime.now() > self.EXPIRES_AT

    def is_active(self):
        """检查是否可用"""
        return self.STATUS == 1 and not self.is_expired()


class APIKEYLOG(Base):
    """
    API Key 使用记录表
    记录每次 API Key 的使用情况
    """
    __tablename__ = 'API_KEY_LOGS'

    ID = Column(Integer, primary_key=True)
    # 关联的 API Key ID
    API_KEY_ID = Column(Integer, nullable=False, index=True)
    # 请求ID
    REQUEST_ID = Column(String(64), nullable=False, unique=True, index=True)
    # 请求名称/描述
    REQUEST_NAME = Column(String(255), nullable=True)
    # 来源IP
    SOURCE_IP = Column(String(64), nullable=True)
    # 来源用户代理
    USER_AGENT = Column(Text, nullable=True)
    # 请求路径
    REQUEST_PATH = Column(String(512), nullable=True)
    # 请求方法
    REQUEST_METHOD = Column(String(10), nullable=True)
    # 状态: 1=成功, 0=失败
    STATUS = Column(Integer, default=1, nullable=False)
    # 响应状态码
    RESPONSE_CODE = Column(Integer, nullable=True)
    # 错误信息
    ERROR_MESSAGE = Column(Text, nullable=True)
    # 请求时间
    REQUEST_AT = Column(DateTime, default=datetime.now, nullable=False)
    # 响应时间(毫秒)
    RESPONSE_TIME_MS = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_API_KEY_LOGS_API_KEY_ID', 'API_KEY_ID'),
        Index('ix_API_KEY_LOGS_REQUEST_AT', 'REQUEST_AT'),
        Index('ix_API_KEY_LOGS_STATUS', 'STATUS'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.ID,
            'api_key_id': self.API_KEY_ID,
            'request_id': self.REQUEST_ID,
            'request_name': self.REQUEST_NAME,
            'source_ip': self.SOURCE_IP,
            'user_agent': self.USER_AGENT,
            'request_path': self.REQUEST_PATH,
            'request_method': self.REQUEST_METHOD,
            'status': self.STATUS,
            'response_code': self.RESPONSE_CODE,
            'error_message': self.ERROR_MESSAGE,
            'request_at': self.REQUEST_AT.isoformat() if self.REQUEST_AT else None,
            'response_time_ms': self.RESPONSE_TIME_MS,
        }
