"""定稿幂等收据仓储."""

import time

from sqlalchemy.exc import IntegrityError

from app.db.models.finalize_receipt import FinalizeReceipt
from app.db.repositories.base_repository import BaseRepository


class FinalizeReceiptRepository(BaseRepository):
    def claim(self, receipt_key: str) -> bool:
        """抢占收据；已存在说明该定稿已处理过."""
        with self.session() as db:
            try:
                db.add(
                    FinalizeReceipt(
                        RECEIPT_KEY=receipt_key,
                        CREATED_AT=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )
                db.flush()
                return True
            except IntegrityError:
                db.rollback()
                return False
