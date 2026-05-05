# -*- coding: utf-8 -*-
"""
系统字典 Repository
底层数据访问
"""
from typing import List, Optional

from app.db.models.system import SYSTEMDICT
from app.db.repositories.base_repository import BaseRepository


class SystemDictRepository(BaseRepository):
    """系统字典仓储"""

    def get_by_type_key(self, dtype: str, key: str) -> Optional[SYSTEMDICT]:
        """根据 type + key 获取记录"""
        return self._db.query(SYSTEMDICT).filter(
            SYSTEMDICT.TYPE == dtype, SYSTEMDICT.KEY == key
        ).first()

    def list_by_type(self, dtype: str) -> List[SYSTEMDICT]:
        """根据 type 获取列表"""
        return self._db.query(SYSTEMDICT).filter(SYSTEMDICT.TYPE == dtype).all()

    def set(self, dtype: str, key: str, value: str, note: str = "") -> bool:
        """设置字典值（存在则更新，不存在则插入）"""
        existing = self.get_by_type_key(dtype, key)
        if existing:
            existing.VALUE = value
            if note:
                existing.NOTE = note
        else:
            self._db.insert(SYSTEMDICT(TYPE=dtype, KEY=key, VALUE=value, NOTE=note))
        self._db.commit()
        return True

    def delete(self, dtype: str, key: str) -> bool:
        """删除字典值"""
        result = self._db.query(SYSTEMDICT).filter(
            SYSTEMDICT.TYPE == dtype, SYSTEMDICT.KEY == key
        ).delete()
        self._db.commit()
        return result > 0

    def exists(self, dtype: str, key: str) -> bool:
        """检查是否存在"""
        count = self._db.query(SYSTEMDICT).filter(
            SYSTEMDICT.TYPE == dtype, SYSTEMDICT.KEY == key
        ).count()
        return count > 0
