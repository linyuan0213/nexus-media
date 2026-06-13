"""
RBAC Repository
基于角色的访问控制(RBAC)数据访问层
处理用户、角色、权限、菜单的数据库操作
"""

from sqlalchemy import desc

from app.db.models.rbac import (
    RBACOperationLog,
    RBACUserLoginLog,
)
from app.db.repositories.base_repository import BaseRepository


class RBACLogRepository(BaseRepository):
    """
    RBAC日志管理仓储
    """

    # ========== 登录日志 ==========

    def add_login_log(
        self,
        user_id: int | None,
        username: str,
        login_ip: str | None = None,
        login_location: str | None = None,
        user_agent: str | None = None,
        login_type: str = "password",
        login_status: int = 1,
        fail_reason: str | None = None,
    ) -> RBACUserLoginLog:
        """
        添加登录日志
        """
        with self.session() as db:
            log = RBACUserLoginLog(
                USER_ID=user_id,
                USERNAME=username,
                LOGIN_IP=login_ip,
                LOGIN_LOCATION=login_location,
                USER_AGENT=user_agent,
                LOGIN_TYPE=login_type,
                LOGIN_STATUS=login_status,
                FAIL_REASON=fail_reason,
            )
            db.add(log)
            db.commit()
            return log

    def get_login_logs(self, user_id: int | None = None, page: int = 1, page_size: int = 20) -> tuple:
        """
        获取登录日志
        """
        with self.session() as db:
            query = db.query(RBACUserLoginLog)

            if user_id:
                query = query.filter(RBACUserLoginLog.USER_ID == user_id)

            total = query.count()
            logs = query.order_by(desc(RBACUserLoginLog.LOGIN_AT)).offset((page - 1) * page_size).limit(page_size).all()

            return logs, total

    # ========== 操作日志 ==========

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
    ) -> RBACOperationLog:
        """
        添加操作日志
        """
        with self.session() as db:
            log = RBACOperationLog(
                USER_ID=user_id,
                USERNAME=username,
                MODULE=module,
                OPERATION_TYPE=operation_type,
                DESCRIPTION=description,
                REQUEST_METHOD=request_method,
                REQUEST_URL=request_url,
                REQUEST_PARAMS=request_params,
                RESPONSE_DATA=response_data,
                OPERATION_IP=operation_ip,
                EXECUTION_TIME=execution_time,
                OPERATION_STATUS=operation_status,
                ERROR_MSG=error_msg,
            )
            db.add(log)
            db.commit()
            return log

    def get_operation_logs(
        self, user_id: int | None = None, module: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple:
        """
        获取操作日志
        """
        with self.session() as db:
            query = db.query(RBACOperationLog)

            if user_id:
                query = query.filter(user_id == RBACOperationLog.USER_ID)
            if module:
                query = query.filter(RBACOperationLog.MODULE == module)

            total = query.count()
            logs = (
                query.order_by(desc(RBACOperationLog.OPERATED_AT)).offset((page - 1) * page_size).limit(page_size).all()
            )

            return logs, total
