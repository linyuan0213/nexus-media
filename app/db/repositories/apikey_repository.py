"""
API Key Repository
API Key 数据访问层
"""

from datetime import datetime

from sqlalchemy import desc, func

from app.db.models.apikey import APIKEY, APIKEYLOG
from app.db.repositories.base_repository import BaseRepository


class APIKeyRepository(BaseRepository):
    """API Key 管理仓储"""

    def get_by_id(self, key_id: int) -> APIKEY | None:
        """根据 ID 获取 API Key"""
        return self._db.query(APIKEY).filter(key_id == APIKEY.ID).first()

    def get_by_key_value(self, key_value: str) -> APIKEY | None:
        """根据 Key 值获取 API Key"""
        return self._db.query(APIKEY).filter(key_value == APIKEY.KEY_VALUE).first()

    def get_by_key_and_status(self, key_value: str, status: int = 1) -> APIKEY | None:
        """根据 Key 值和状态获取 API Key"""
        return self._db.query(APIKEY).filter(key_value == APIKEY.KEY_VALUE, status == APIKEY.STATUS).first()

    def get_by_name(self, name: str, status: int | None = None) -> APIKEY | None:
        """根据名称获取 API Key"""
        query = self._db.query(APIKEY).filter(name == APIKEY.NAME)
        if status is not None:
            query = query.filter(status == APIKEY.STATUS)
        return query.order_by(desc(APIKEY.CREATED_AT)).first()

    def list_keys(self, page: int = 1, page_size: int = 50) -> tuple[list[APIKEY], int]:
        """获取 API Key 列表（支持分页）"""
        query = self._db.query(APIKEY).order_by(desc(APIKEY.CREATED_AT))
        total = query.count()
        items = self._paginate(query, page, page_size).all()
        return items, total

    def create_key(
        self,
        name: str,
        key_value: str,
        key_prefix: str,
        status: int = 1,
        expires_at: datetime | None = None,
        created_by: int | None = None,
        description: str = "",
        raw_key: str | None = None,
    ) -> APIKEY:
        """创建 API Key"""
        api_key = APIKEY(
            NAME=name,
            KEY_VALUE=key_value,
            KEY_PREFIX=key_prefix,
            STATUS=status,
            EXPIRES_AT=expires_at,
            CREATED_BY=created_by,
            DESCRIPTION=description,
            RAW_KEY=raw_key,
        )
        self._db.insert(api_key)
        self._db.commit()
        self._db.session.refresh(api_key)
        return api_key

    def update_key(self, key_id: int, **kwargs) -> bool:
        """更新 API Key"""
        key = self.get_by_id(key_id)
        if not key:
            return False
        for k, v in kwargs.items():
            if hasattr(key, k.upper()):
                setattr(key, k.upper(), v)
        self._db.commit()
        return True

    def delete_key(self, key_id: int) -> bool:
        """删除 API Key"""
        key = self.get_by_id(key_id)
        if not key:
            return False
        # 删除关联的使用记录
        self._db.query(APIKEYLOG).filter(key_id == APIKEYLOG.API_KEY_ID).delete()
        self._db.session.delete(key)
        self._db.commit()
        return True

    def increment_use_count(self, key_id: int) -> bool:
        """增加使用次数"""
        key = self.get_by_id(key_id)
        if not key:
            return False
        key.USE_COUNT = (key.USE_COUNT or 0) + 1
        key.LAST_USED_AT = datetime.now()
        self._db.commit()
        return True

    def get_stats(self) -> dict[str, int]:
        """获取统计信息"""
        total_keys = self._db.query(func.count(APIKEY.ID)).scalar() or 0
        active_keys = self._db.query(func.count(APIKEY.ID)).filter(APIKEY.STATUS == 1).scalar() or 0
        total_requests = self._db.query(func.count(APIKEYLOG.ID)).scalar() or 0
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_requests = self._db.query(func.count(APIKEYLOG.ID)).filter(today <= APIKEYLOG.REQUEST_AT).scalar() or 0
        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_requests": total_requests,
            "today_requests": today_requests,
        }


class APIKeyLogRepository(BaseRepository):
    """API Key 使用记录仓储"""

    def create_log(
        self,
        api_key_id: int,
        request_id: str,
        request_name: str = "",
        source_ip: str = "",
        user_agent: str = "",
        request_path: str = "",
        request_method: str = "",
        status: int = 1,
        response_code: int | None = None,
        error_message: str = "",
        response_time_ms: int | None = None,
    ) -> APIKEYLOG:
        """创建使用记录"""
        log_entry = APIKEYLOG(
            API_KEY_ID=api_key_id,
            REQUEST_ID=request_id,
            REQUEST_NAME=request_name,
            SOURCE_IP=source_ip,
            USER_AGENT=user_agent,
            REQUEST_PATH=request_path,
            REQUEST_METHOD=request_method,
            STATUS=status,
            RESPONSE_CODE=response_code,
            ERROR_MESSAGE=error_message,
            RESPONSE_TIME_MS=response_time_ms,
        )
        self._db.insert(log_entry)
        self._db.commit()
        self._db.session.refresh(log_entry)
        return log_entry

    def list_logs(
        self, api_key_id: int | None = None, page: int = 1, page_size: int = 50
    ) -> tuple[list[APIKEYLOG], int]:
        """获取使用记录列表"""
        query = self._db.query(APIKEYLOG).order_by(desc(APIKEYLOG.REQUEST_AT))
        if api_key_id is not None:
            query = query.filter(api_key_id == APIKEYLOG.API_KEY_ID)
        total = query.count()
        items = self._paginate(query, page, page_size).all()
        return items, total

    def get_log_by_request_id(self, request_id: str) -> APIKEYLOG | None:
        """根据请求 ID 获取记录"""
        return self._db.query(APIKEYLOG).filter(request_id == APIKEYLOG.REQUEST_ID).first()

    def delete_logs_by_key_id(self, api_key_id: int) -> int:
        """删除指定 API Key 的所有记录"""
        result = self._db.query(APIKEYLOG).filter(api_key_id == APIKEYLOG.API_KEY_ID).delete()
        self._db.commit()
        return result
