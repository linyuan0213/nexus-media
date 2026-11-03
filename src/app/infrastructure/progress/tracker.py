"""
进度追踪器
"""

from enum import Enum
from typing import Union

import log
from app.domain.enums import ProgressKey


class ProgressTracker:
    _process_detail: dict = {}

    def __init__(self):
        pass

    def __reset(self, ptype: ProgressKey | Union[str, None] = ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        self._process_detail[ptype] = {"enable": False, "value": 0, "text": "请稍候..."}

    def start(self, ptype: ProgressKey | str = ProgressKey.Search):
        self.__reset(ptype)
        if isinstance(ptype, Enum):
            ptype = ptype.value
        self._process_detail[ptype]["enable"] = True
        log.debug(f"[ProgressTracker] start: key={ptype}")

    def end(self, ptype: ProgressKey | str = ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        if not self._process_detail.get(ptype):
            return
        self._process_detail[ptype]["value"] = 100
        self._process_detail[ptype]["text"] = "处理完成"
        self._process_detail[ptype]["enable"] = False
        log.debug(f"[ProgressTracker] end: key={ptype}")

    def update(self, value=None, text=None, ptype: ProgressKey | str = ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        detail = self._process_detail.get(ptype, {})
        enabled = detail.get("enable")
        if not enabled:
            return
        if value is not None:
            detail["value"] = value
        if text is not None:
            detail["text"] = text

    def update_max(self, value=None, text=None, ptype: ProgressKey | str = ProgressKey.Search):
        """值只增不减的更新 — 多并发写同一 key 时保持进度单调"""
        key = ptype.value if isinstance(ptype, Enum) else ptype
        detail = self._process_detail.get(key, {})
        if value is not None and value < detail.get("value", 0):
            value = detail["value"]
        self.update(value=value, text=text, ptype=ptype)

    def get_process(self, ptype: ProgressKey | str = ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        detail = self._process_detail.get(ptype)
        if not detail:
            return None
        return detail


class ScopedProgressTracker:
    """把 0-100 的局部阶段进度映射到父进度的区间。"""

    def __init__(self, tracker: ProgressTracker, ptype, base: float, span: float):
        self._tracker = tracker
        self._ptype = ptype
        self._base = max(0.0, float(base))
        self._span = max(0.0, float(span))

    def _value(self, value: float) -> int:
        return round(self._base + self._span * max(0.0, min(100.0, float(value))) / 100)

    def update(self, value=None, text=None, ptype=None):
        if value is not None:
            value = self._value(value)
        self._tracker.update_max(value=value, text=text, ptype=self._ptype)

    def update_max(self, value=None, text=None, ptype=None):
        if value is not None:
            value = self._value(value)
        self._tracker.update_max(value=value, text=text, ptype=self._ptype)

    def get_process(self, ptype=None):
        return self._tracker.get_process(self._ptype)
