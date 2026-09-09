"""数据归属行级过滤（L2 数据权限）.

统一收敛点：repository 查询经 apply_owner_scope 过滤，写操作经 assert_owner 校验。
superadmin 角色全量可见；普通用户仅可见归属自己的行。
"""

from typing import Any

from sqlalchemy import or_

from app.schemas.auth import UserContext


def apply_owner_scope(query, model: Any, user: UserContext, *, include_shared: bool = False):
    """按数据归属过滤查询.

    Args:
        query: SQLAlchemy 查询对象
        model: 含 USER_ID 列的模型类
        user: 当前用户上下文
        include_shared: True 时 NULL（系统/后台产生）行对所有用户可见
                        （搜索结果、下载历史等共享语义）；False 时仅 superadmin 可见
                        （订阅等愿望单数据）
    """
    if user.is_superadmin:
        return query
    condition = model.USER_ID == user.user_id
    if include_shared:
        condition = or_(condition, model.USER_ID.is_(None))
    return query.where(condition)


def is_owner(row_user_id: int | None, user: UserContext) -> bool:
    """判断行是否归当前用户所有（superadmin 恒真；NULL 行普通用户不可写）."""
    if user.is_superadmin:
        return True
    return row_user_id is not None and row_user_id == user.user_id
