"""订阅数据归属隔离集成测试（真实 SQLite，验证 ADR-021 测试矩阵）."""

from app.db.models import SubscribeMovies, SubscribeTvs
from app.db.repositories.data_scope import apply_owner_scope
from app.schemas.auth import UserContext, system_user_context


def _user(user_id: int) -> UserContext:
    return UserContext(user_id=user_id, username=f"u{user_id}", level=0, permissions=[], role_codes=["user"])


def _seed(db_session):
    rows = [
        SubscribeMovies(NAME="MovieA", YEAR="2024", USER_ID=1),
        SubscribeMovies(NAME="MovieB", YEAR="2024", USER_ID=2),
        SubscribeMovies(NAME="MovieSystem", YEAR="2024", USER_ID=None),
        SubscribeTvs(NAME="TvA", YEAR="2024", SEASON="S01", USER_ID=1),
        SubscribeTvs(NAME="TvB", YEAR="2024", SEASON="S01", USER_ID=2),
    ]
    db_session.add_all(rows)
    db_session.commit()


class TestSubscribeOwnershipScope:
    def test_user_sees_only_own_movies(self, db_session):
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeMovies), SubscribeMovies, _user(1))
        names = {m.NAME for m in query.all()}
        assert names == {"MovieA"}

    def test_other_user_invisible(self, db_session):
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeMovies), SubscribeMovies, _user(2))
        names = {m.NAME for m in query.all()}
        assert names == {"MovieB"}

    def test_system_owned_subscription_invisible_to_normal_user(self, db_session):
        """订阅类 NULL（系统/插件创建）行仅 superadmin 可见"""
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeMovies), SubscribeMovies, _user(1))
        assert all(m.USER_ID is not None for m in query.all())

    def test_superadmin_sees_all(self, db_session):
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeMovies), SubscribeMovies, system_user_context())
        assert len(query.all()) == 3

    def test_tv_scope(self, db_session):
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeTvs), SubscribeTvs, _user(2))
        assert {t.NAME for t in query.all()} == {"TvB"}

    def test_shared_tables_include_null(self, db_session):
        """include_shared=True（搜索/下载历史语义）时 NULL 行全局可见"""
        _seed(db_session)
        query = apply_owner_scope(db_session.query(SubscribeMovies), SubscribeMovies, _user(1), include_shared=True)
        names = {m.NAME for m in query.all()}
        assert names == {"MovieA", "MovieSystem"}


class TestSubscribeUniqueConstraint:
    def test_same_user_duplicate_rejected(self, db_session):
        """同用户重复订阅同媒体触发唯一约束"""
        from sqlalchemy.exc import IntegrityError

        db_session.add(SubscribeMovies(NAME="MovieA", YEAR="2024", TMDBID="100", USER_ID=1))
        db_session.commit()
        db_session.add(SubscribeMovies(NAME="MovieA", YEAR="2024", TMDBID="100", USER_ID=1))
        try:
            db_session.commit()
            raise AssertionError("unique constraint not enforced")
        except IntegrityError:
            db_session.rollback()

    def test_cross_user_same_media_allowed(self, db_session):
        """跨用户订阅同媒体合法"""
        db_session.add(SubscribeMovies(NAME="MovieA", YEAR="2024", TMDBID="100", USER_ID=1))
        db_session.add(SubscribeMovies(NAME="MovieA", YEAR="2024", TMDBID="100", USER_ID=2))
        db_session.commit()
        assert db_session.query(SubscribeMovies).count() == 2
