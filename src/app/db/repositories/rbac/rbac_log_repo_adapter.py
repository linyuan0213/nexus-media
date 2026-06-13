"""
RBAC 领域 Repository 适配器
将旧版 RBACRepository 适配为新领域接口
"""

from typing import cast

from app.db.repositories.rbac.rbac_log_repository import RBACLogRepository
from app.domain.entities.rbac import (
    RBACOperationLogEntity,
    RBACUserLoginLogEntity,
)
from app.domain.interfaces.rbac_repo import (
    IRBACLogRepository,
)


class RBACLogRepositoryAdapter(IRBACLogRepository):
    """RBAC日志仓储适配器"""

    def __init__(self, repo: RBACLogRepository | None = None):
        self._repo = repo or RBACLogRepository()

    def add_login_log(
        self,
        user_id: int,
        username: str,
        login_ip: str | None = None,
        login_location: str | None = None,
        user_agent: str | None = None,
        login_type: str = "password",
        login_status: int = 1,
        fail_reason: str | None = None,
    ) -> RBACUserLoginLogEntity:
        row = self._repo.add_login_log(
            user_id, username, login_ip, login_location, user_agent, login_type, login_status, fail_reason
        )
        if isinstance(row, bool):
            row = None
        return cast(RBACUserLoginLogEntity, RBACUserLoginLogEntity.from_orm(row))

    def get_login_logs(
        self, user_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[RBACUserLoginLogEntity], int]:
        rows, total = self._repo.get_login_logs(user_id=user_id, page=page, page_size=page_size)
        return [e for e in [RBACUserLoginLogEntity.from_orm(r) for r in rows] if e is not None], total

    def add_operation_log(
        self,
        user_id: int | None = None,
        username: str | None = None,
        module: str | None = None,
        operation_type: str = "QUERY",
        description: str | None = None,
        request_method: str | None = None,
        request_url: str | None = None,
        request_params: str | None = None,
        response_data: str | None = None,
        operation_ip: str | None = None,
        execution_time: int | None = None,
        operation_status: int = 1,
        error_msg: str | None = None,
    ) -> RBACOperationLogEntity:
        row = self._repo.add_operation_log(
            user_id,
            username,
            module,
            operation_type,
            description,
            request_method,
            request_url,
            request_params,
            response_data,
            operation_ip,
            execution_time,
            operation_status,
            error_msg,
        )
        if isinstance(row, bool):
            row = None
        return cast(RBACOperationLogEntity, RBACOperationLogEntity.from_orm(row))

    def get_operation_logs(
        self, user_id: int | None = None, module: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[RBACOperationLogEntity], int]:
        rows, total = self._repo.get_operation_logs(user_id=user_id, module=module, page=page, page_size=page_size)
        return [e for e in [RBACOperationLogEntity.from_orm(r) for r in rows] if e is not None], total
