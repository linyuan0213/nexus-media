"""用户/角色删除时的归属数据清理（ADR-021 5.7）.

SQLite 默认未开启 PRAGMA foreign_keys，外键级联不生效；
服务层显式清理，保证删除用户/角色后不留孤儿数据（MySQL 下与 DB 级联等价）。
"""

from sqlalchemy import Integer, cast

import log
from app.db.models import (
    RBACRoleSite,
    RBACUserChannel,
    RBACUserSite,
    SubscribeHistory,
    SubscribeMovies,
    SubscribeTvEpisodes,
    SubscribeTvs,
)
from app.db.models.config import CONFIGUSERRSS
from app.db.models.download import DOWNLOADHISTORY
from app.db.models.plugin import USERRSSTASKHISTORY
from app.db.models.search import SEARCHRESULTINFO
from app.db.repositories.base_repository import BaseRepository


class OwnedDataCleaner(BaseRepository):
    """归属数据清理器"""

    def purge_user(self, user_id: int) -> None:
        """删除用户归属数据：业务行删除，历史类归属置空."""
        with self.session() as db:
            # 订阅剧集进度按父订阅 RSSID 关联，需先删（部分行 USER_ID 可能为空）
            tv_rssids = [row.ID for row in db.query(SubscribeTvs.ID).filter(SubscribeTvs.USER_ID == user_id).all()]
            if tv_rssids:
                db.query(SubscribeTvEpisodes).filter(
                    cast(SubscribeTvEpisodes.RSSID, Integer).in_([int(r) for r in tv_rssids])
                ).delete(synchronize_session=False)
            db.query(SubscribeMovies).filter(SubscribeMovies.USER_ID == user_id).delete()
            db.query(SubscribeTvs).filter(SubscribeTvs.USER_ID == user_id).delete()
            db.query(SubscribeHistory).filter(SubscribeHistory.USER_ID == user_id).delete()
            db.query(SubscribeTvEpisodes).filter(SubscribeTvEpisodes.USER_ID == user_id).delete()
            db.query(CONFIGUSERRSS).filter(CONFIGUSERRSS.USER_ID == user_id).delete()
            db.query(RBACUserSite).filter(RBACUserSite.USER_ID == user_id).delete()
            db.query(RBACUserChannel).filter(RBACUserChannel.USER_ID == user_id).delete()
            # 搜索结果属临时数据，直接删除
            db.query(SEARCHRESULTINFO).filter(SEARCHRESULTINFO.USER_ID == str(user_id)).delete()
            # 历史/审计类保留行，仅解除归属
            db.query(USERRSSTASKHISTORY).filter(USERRSSTASKHISTORY.USER_ID == user_id).update(
                {USERRSSTASKHISTORY.USER_ID: None}
            )
            db.query(DOWNLOADHISTORY).filter(DOWNLOADHISTORY.USER_ID == user_id).update({DOWNLOADHISTORY.USER_ID: None})
        log.info(f"[RBAC]已清理用户 {user_id} 的归属数据")

    def purge_role(self, role_id: int) -> None:
        """删除角色归属数据（站点授权）."""
        with self.session() as db:
            db.query(RBACRoleSite).filter(RBACRoleSite.ROLE_ID == role_id).delete()
        log.info(f"[RBAC]已清理角色 {role_id} 的站点授权")


# 模块级单例复用（无状态）
_cleaner: OwnedDataCleaner | None = None


def get_owned_data_cleaner() -> OwnedDataCleaner:
    global _cleaner
    if _cleaner is None:
        _cleaner = OwnedDataCleaner()
    return _cleaner
