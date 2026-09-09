"""数据归属行级过滤（data_scope）测试."""

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.repositories.data_scope import apply_owner_scope, is_owner
from app.schemas.auth import UserContext, system_user_context


class _OwnedModel(Base):
    __tablename__ = "TEST_OWNED_MODEL"

    ID: Mapped[int] = mapped_column(Integer, primary_key=True)
    USER_ID: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


def _user(user_id: int = 7, role_codes: list[str] | None = None) -> UserContext:
    return UserContext(
        user_id=user_id,
        username=f"u{user_id}",
        level=0,
        permissions=[],
        role_codes=role_codes or ["user"],
    )


def _superadmin() -> UserContext:
    return system_user_context()


class TestApplyOwnerScope:
    def test_superadmin_bypasses_filter(self):
        query = apply_owner_scope(_FakeQuery(), _OwnedModel, _superadmin())
        assert query.conditions == []

    def test_normal_user_filtered_by_user_id(self):
        query = apply_owner_scope(_FakeQuery(), _OwnedModel, _user(7))
        assert len(query.conditions) == 1
        assert "USER_ID" in str(query.conditions[0])
        assert "IS NULL" not in str(query.conditions[0]).upper()

    def test_include_shared_allows_null_rows(self):
        query = apply_owner_scope(_FakeQuery(), _OwnedModel, _user(7), include_shared=True)
        assert len(query.conditions) == 1
        assert "IS NULL" in str(query.conditions[0]).upper()


class TestIsOwner:
    def test_superadmin_always_owner(self):
        assert is_owner(99, _superadmin())
        assert is_owner(None, _superadmin())

    def test_owner_match(self):
        assert is_owner(7, _user(7))

    def test_not_owner(self):
        assert not is_owner(8, _user(7))

    def test_null_row_not_writable_by_normal_user(self):
        assert not is_owner(None, _user(7))


class _FakeQuery:
    """最小查询替身：记录 where 条件."""

    def __init__(self):
        self.conditions: list = []

    def where(self, *conditions):
        self.conditions.extend(conditions)
        return self


class TestSystemContext:
    def test_system_context_is_superadmin(self):
        ctx = system_user_context()
        assert ctx.is_superadmin
        assert ctx.user_id == 0

    def test_contexts_are_independent(self):
        a = system_user_context()
        b = system_user_context()
        a.role_codes.append("mutated")
        assert "mutated" not in b.role_codes
