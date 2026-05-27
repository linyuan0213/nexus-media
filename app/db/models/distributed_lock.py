"""
分布式锁模型
包含: 分布式锁记录表
"""

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DISTRIBUTEDLOCK(Base):
    __tablename__ = "DISTRIBUTED_LOCK"
    __table_args__ = (Index("INDX_DISTRIBUTED_LOCK_EXPIRES", "EXPIRES_AT"),)

    LOCK_KEY: Mapped[str] = mapped_column(String(255), primary_key=True)
    TOKEN: Mapped[str] = mapped_column(String(255), nullable=False)
    INSTANCE: Mapped[str] = mapped_column(String(255), nullable=False)
    EXPIRES_AT: Mapped[int] = mapped_column(Integer, nullable=False)
