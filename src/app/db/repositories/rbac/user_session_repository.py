"""用户设备会话仓储."""

from datetime import datetime
from typing import Any

from app.db.models.rbac import RBACUserSession
from app.db.repositories.base_repository import BaseRepository


class RBACUserSessionRepository(BaseRepository):
    """服务端会话：记录设备/IP，并支持主动吊销."""

    def create_session(
        self,
        session_id: str,
        user_id: int,
        refresh_jti: str,
        *,
        device: dict[str, Any],
        login_ip: str | None,
        user_agent: str | None,
        expires_at: datetime,
    ) -> dict[str, Any]:
        with self.session() as db:
            row = RBACUserSession(
                SESSION_ID=session_id,
                USER_ID=user_id,
                REFRESH_JTI=refresh_jti,
                DEVICE_TYPE=device.get("device_type"),
                DEVICE_MODEL=device.get("device_model"),
                OS_NAME=device.get("os"),
                BROWSER=device.get("browser"),
                LOGIN_IP=login_ip,
                USER_AGENT=user_agent,
                EXPIRES_AT=expires_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def get_active_session(self, session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        now = datetime.now()
        with self.readonly() as db:
            query = db.query(RBACUserSession).filter(
                RBACUserSession.SESSION_ID == session_id,
                RBACUserSession.REVOKED_AT.is_(None),
                RBACUserSession.EXPIRES_AT > now,
            )
            if user_id is not None:
                query = query.filter(RBACUserSession.USER_ID == user_id)
            row = query.first()
            return row.to_dict() if row else None

    def touch_session(
        self,
        session_id: str,
        *,
        refresh_jti: str | None = None,
        login_ip: str | None = None,
    ) -> bool:
        with self.session() as db:
            row = db.query(RBACUserSession).filter(RBACUserSession.SESSION_ID == session_id).first()
            if row is None:
                return False
            row.LAST_SEEN_AT = datetime.now()
            if login_ip:
                row.LOGIN_IP = login_ip
            if refresh_jti:
                row.REFRESH_JTI = refresh_jti
            db.commit()
            return True

    def revoke_session(
        self,
        session_id: str,
        *,
        user_id: int | None = None,
        reason: str = "logout",
    ) -> bool:
        with self.session() as db:
            query = db.query(RBACUserSession).filter(
                RBACUserSession.SESSION_ID == session_id,
                RBACUserSession.REVOKED_AT.is_(None),
            )
            if user_id is not None:
                query = query.filter(RBACUserSession.USER_ID == user_id)
            row = query.first()
            if row is None:
                return False
            row.REVOKED_AT = datetime.now()
            row.REVOKE_REASON = reason
            db.commit()
            return True

    def revoke_other_sessions(self, user_id: int, keep_session_id: str, *, reason: str = "revoke_others") -> int:
        with self.session() as db:
            rows = (
                db.query(RBACUserSession)
                .filter(
                    RBACUserSession.USER_ID == user_id,
                    RBACUserSession.SESSION_ID != keep_session_id,
                    RBACUserSession.REVOKED_AT.is_(None),
                )
                .all()
            )
            now = datetime.now()
            for row in rows:
                row.REVOKED_AT = now
                row.REVOKE_REASON = reason
            db.commit()
            return len(rows)

    def list_sessions(self, user_id: int) -> list[dict[str, Any]]:
        """只返回当前有效会话；已吊销/过期会话不再展示."""
        now = datetime.now()
        with self.readonly() as db:
            rows = (
                db.query(RBACUserSession)
                .filter(
                    RBACUserSession.USER_ID == user_id,
                    RBACUserSession.REVOKED_AT.is_(None),
                    RBACUserSession.EXPIRES_AT > now,
                )
                .order_by(RBACUserSession.LAST_SEEN_AT.desc())
                .all()
            )
            return [row.to_dict() for row in rows]
