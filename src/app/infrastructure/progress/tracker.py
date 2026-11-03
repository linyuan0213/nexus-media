"""
进度追踪器
"""

import threading
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
        self._process_detail[ptype] = {"enable": False, "value": 1, "text": "初始化..."}

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


class CompositeProgress:
    """单个子任务进度，写入父级 CompositeProgressGroup。"""

    def __init__(self, group: "CompositeProgressGroup", index: int):
        self._group = group
        self._index = index

    def update(self, value=None, text=None, ptype=None):
        if value is not None:
            self._group.set_child(self._index, value, text)

    def update_max(self, value=None, text=None, ptype=None):
        if value is not None:
            self._group.set_child(self._index, value, text)

    def get_process(self, ptype=None):
        return self._group.get_process()


class CompositeProgressGroup:
    """多关键词并发搜索的根进度：百分比取子任务平均值。"""

    def __init__(self, tracker: ProgressTracker, ptype, total: int, title: str = "搜索"):
        self._tracker = tracker
        self._ptype = ptype.value if isinstance(ptype, Enum) else ptype
        self._total = max(1, int(total))
        self._title = title
        self._values = [0.0] * self._total
        self._texts = [""] * self._total
        self._completed = 0
        self._lock = threading.RLock()
        tracker.update_max(value=1, text=f"{title}：准备 {self._total} 个关键词...", ptype=self._ptype)

    def child(self, index: int) -> CompositeProgress:
        return CompositeProgress(self, index)

    def set_child(self, index: int, value: float, text: str | None = None):
        with self._lock:
            if not 0 <= index < self._total:
                return
            self._values[index] = max(self._values[index], max(0.0, min(100.0, float(value))))
            if text:
                self._texts[index] = text
            average = sum(self._values) / self._total
            detail_text = self._texts[index] or ""
            self._tracker.update_max(
                value=round(average),
                text=f"{self._title} 第 {index + 1}/{self._total} 个关键词 · {detail_text}",
                ptype=self._ptype,
            )

    def complete_child(self, index: int, text: str | None = None):
        with self._lock:
            if not 0 <= index < self._total:
                return
            if self._values[index] < 100:
                self._completed += 1
            self._values[index] = 100.0
            if text:
                self._texts[index] = text
            self._tracker.update_max(
                value=round(sum(self._values) / self._total),
                text=(f"{self._title}：关键词完成 {self._completed}/{self._total}" + (f" · {text}" if text else "")),
                ptype=self._ptype,
            )

    def get_process(self):
        return self._tracker.get_process(self._ptype)
