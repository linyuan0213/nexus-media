"""刮削定稿幂等收据：队列 ACK 重投时避免重复发通知/事件."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FinalizeReceipt(Base):
    __tablename__ = "FINALIZE_RECEIPT"

    RECEIPT_KEY: Mapped[str] = mapped_column(String(512), primary_key=True)
    CREATED_AT: Mapped[str] = mapped_column(String(255), nullable=False)
