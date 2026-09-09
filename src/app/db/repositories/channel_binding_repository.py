"""用户渠道身份绑定 Repository（RBAC_USER_CHANNELS）."""

from datetime import datetime

from app.db.models import RBACUserChannel
from app.db.repositories.base_repository import BaseRepository


class ChannelBindingRepository(BaseRepository):
    """渠道绑定仓储"""

    def get_binding(self, channel: str, channel_user_id: str) -> RBACUserChannel | None:
        """按渠道身份查询绑定"""
        if not channel or not channel_user_id:
            return None
        with self.session() as db:
            return (
                db.query(RBACUserChannel)
                .filter(
                    RBACUserChannel.CHANNEL == channel,
                    RBACUserChannel.CHANNEL_USER_ID == str(channel_user_id),
                    RBACUserChannel.STATUS == 1,
                )
                .first()
            )

    def list_by_user(self, user_id: int) -> list[RBACUserChannel]:
        """查询用户的全部绑定"""
        with self.session() as db:
            return (
                db.query(RBACUserChannel)
                .filter(RBACUserChannel.USER_ID == user_id)
                .order_by(RBACUserChannel.CREATED_AT.desc())
                .all()
            )

    def bind(self, user_id: int, channel: str, channel_user_id: str) -> RBACUserChannel:
        """建立绑定（已存在则复用启用）"""
        with self.session() as db:
            existing = (
                db.query(RBACUserChannel)
                .filter(
                    RBACUserChannel.CHANNEL == channel,
                    RBACUserChannel.CHANNEL_USER_ID == str(channel_user_id),
                )
                .first()
            )
            if existing:
                existing.USER_ID = user_id
                existing.STATUS = 1
                return existing
            row = RBACUserChannel(
                USER_ID=user_id,
                CHANNEL=channel,
                CHANNEL_USER_ID=str(channel_user_id),
                STATUS=1,
                CREATED_AT=datetime.now(),
            )
            db.add(row)
            db.flush()
            return row

    def unbind(self, user_id: int, channel: str, channel_user_id: str) -> bool:
        """解绑（仅可操作自己的绑定）"""
        with self.session() as db:
            deleted = (
                db.query(RBACUserChannel)
                .filter(
                    RBACUserChannel.USER_ID == user_id,
                    RBACUserChannel.CHANNEL == channel,
                    RBACUserChannel.CHANNEL_USER_ID == str(channel_user_id),
                )
                .delete()
            )
            return deleted > 0

    def unbind_by_id(self, binding_id: int) -> bool:
        """管理员按 ID 强制解绑"""
        with self.session() as db:
            return db.query(RBACUserChannel).filter(RBACUserChannel.ID == binding_id).delete() > 0

    def list_all(self, channel: str | None = None) -> list[RBACUserChannel]:
        """查询全部绑定（管理视角）"""
        with self.session() as db:
            query = db.query(RBACUserChannel)
            if channel:
                query = query.filter(RBACUserChannel.CHANNEL == channel)
            return query.order_by(RBACUserChannel.CREATED_AT.desc()).all()
