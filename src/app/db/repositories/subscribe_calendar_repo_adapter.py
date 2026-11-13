"""订阅日历事件仓储：整用户替换，接口只读."""

from __future__ import annotations

import datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

import log
from app.db.models.subscribe import SubscribeCalendarEvent
from app.db.repositories.subscribe_repository import SubscribeRepository
from app.utils.json_utils import JsonUtils


class SubscribeCalendarRepositoryAdapter:
    def __init__(self, repo: SubscribeRepository | None = None):
        self._repo = repo or SubscribeRepository()

    @staticmethod
    def _key(event: dict) -> str:
        return str(event.get("id") or f"{event.get('start')}:{event.get('title')}")

    def get_user_events(self, user_id: int) -> list[dict]:
        try:
            with self._repo.session() as db:
                rows = (
                    db.query(SubscribeCalendarEvent)
                    .filter(SubscribeCalendarEvent.USER_ID == int(user_id or 0))
                    .order_by(SubscribeCalendarEvent.START, SubscribeCalendarEvent.EVENT_KEY)
                    .all()
                )
                result = []
                for row in rows:
                    try:
                        data = JsonUtils.loads(row.DATA)
                    except Exception:
                        continue
                    if isinstance(data, dict):
                        result.append(data)
                return result
        except SQLAlchemyError as exc:
            log.warn(f"[Calendar]读取数据库日历失败: {exc}")
            return []

    def get_user_updated_at(self, user_id: int) -> datetime.datetime | None:
        try:
            with self._repo.session() as db:
                return (
                    db.query(func.max(SubscribeCalendarEvent.UPDATED_AT))
                    .filter(SubscribeCalendarEvent.USER_ID == int(user_id or 0))
                    .scalar()
                )
        except SQLAlchemyError:
            return None

    def replace_user_events(self, user_id: int, events: list[dict]) -> None:
        try:
            with self._repo.session() as db:
                self._replace(db, user_id, events)
        except SQLAlchemyError as exc:
            log.warn(f"[Calendar]写入数据库日历失败: {exc}")

    def _replace(self, db, user_id: int, events: list[dict]) -> None:
        db.query(SubscribeCalendarEvent).filter(SubscribeCalendarEvent.USER_ID == int(user_id or 0)).delete(
            synchronize_session=False
        )
        now = datetime.datetime.now()
        seen: set[str] = set()
        for event in events:
            if not event.get("start"):
                continue
            key = self._key(event)
            if key in seen:
                continue
            seen.add(key)
            db.add(
                SubscribeCalendarEvent(
                    USER_ID=int(user_id or 0),
                    EVENT_KEY=key[:255],
                    START=str(event.get("start"))[:10],
                    DATA=JsonUtils.dumps(event, ensure_ascii=False),
                    UPDATED_AT=now,
                )
            )
