"""用户/角色删除归属数据清理测试（ADR-021 5.7）."""

from contextlib import contextmanager
from typing import Any, cast

from app.db.models import (
    RBACRoleSite,
    RBACUserChannel,
    RBACUserSite,
    SubscribeMovies,
    SubscribeTvEpisodes,
    SubscribeTvs,
)
from app.db.models.download import DOWNLOADHISTORY
from app.db.repositories.owned_data_cleanup import OwnedDataCleaner


def _bind_session(cleaner: OwnedDataCleaner, db_session):
    """将清理器的 session 绑定到测试会话."""

    @contextmanager
    def _session():
        yield db_session

    cast(Any, cleaner)._session_manager = type("SM", (), {"session_scope": staticmethod(_session)})()
    return cleaner


class TestOwnedDataCleanup:
    def test_purge_user_removes_business_rows_and_nulls_history(self, db_session):
        db_session.add_all(
            [
                SubscribeMovies(NAME="M", USER_ID=7),
                SubscribeTvs(NAME="T", USER_ID=7),
                RBACUserSite(USER_ID=7, SITE_NAME="siteA"),
                RBACUserChannel(USER_ID=7, CHANNEL="telegram", CHANNEL_USER_ID="123"),
                DOWNLOADHISTORY(
                    TITLE="D",
                    YEAR="2024",
                    TYPE="MOVIE",
                    TMDBID="1",
                    SE="",
                    VOTE="",
                    POSTER="",
                    OVERVIEW="",
                    TORRENT="",
                    ENCLOSURE="",
                    SITE="",
                    DESC="",
                    DOWNLOADER="",
                    DOWNLOAD_ID="",
                    SAVE_PATH="",
                    DATE="2024-01-01",
                    USER_ID=7,
                ),
            ]
        )
        db_session.commit()
        # 剧集进度按父订阅 RSSID 关联
        db_session.add(SubscribeTvs(ID=99, NAME="T2", USER_ID=7))
        db_session.add(SubscribeTvEpisodes(RSSID="99", EPISODES="[]", USER_ID=None))
        db_session.commit()

        cleaner = _bind_session(OwnedDataCleaner(), db_session)
        cleaner.purge_user(7)
        db_session.commit()

        for model in (SubscribeMovies, SubscribeTvs, RBACUserSite, RBACUserChannel):
            assert db_session.query(model).count() == 0, model
        # 剧集进度随父订阅删除
        assert db_session.query(SubscribeTvEpisodes).count() == 0
        # 下载历史保留但归属置空
        assert db_session.query(DOWNLOADHISTORY).count() == 1
        assert db_session.query(DOWNLOADHISTORY).first().USER_ID is None

    def test_purge_role_removes_site_grants(self, db_session):
        db_session.add(RBACRoleSite(ROLE_ID=3, SITE_NAME="siteA"))
        db_session.commit()
        cleaner = _bind_session(OwnedDataCleaner(), db_session)
        cleaner.purge_role(3)
        db_session.commit()
        assert db_session.query(RBACRoleSite).count() == 0
