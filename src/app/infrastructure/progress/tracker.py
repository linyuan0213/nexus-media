"""
进度追踪器
"""

from enum import Enum

import log
from app.domain.enums import ProgressKey


class ProgressTracker:
    _process_detail: dict = {}

    def __init__(self):
        pass

    def __reset(self, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        self._process_detail[ptype] = {"enable": False, "value": 0, "text": "请稍候..."}

    def start(self, ptype=ProgressKey.Search):
        self.__reset(ptype)
        if isinstance(ptype, Enum):
            ptype = ptype.value
        self._process_detail[ptype]["enable"] = True
        log.debug(f"[ProgressTracker] start: key={ptype}")

    def end(self, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        if not self._process_detail.get(ptype):
            return
        self._process_detail[ptype]["value"] = 100
        self._process_detail[ptype]["text"] = "处理完成"
        self._process_detail[ptype]["enable"] = False
        log.debug(f"[ProgressTracker] end: key={ptype}")

    def update(self, value=None, text=None, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        detail = self._process_detail.get(ptype, {})
        enabled = detail.get("enable")
        if not enabled:
            log.debug(f"[ProgressTracker] update skip (enable=False): key={ptype}")
            return
        if value is not None:
            detail["value"] = value
        if text is not None:
            detail["text"] = text
        log.debug(f"[ProgressTracker] update: key={ptype} value={value}")

    def get_process(self, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        detail = self._process_detail.get(ptype)
        if not detail:
            log.debug(f"[ProgressTracker] get_process None: key={ptype}")
            return None
        log.debug(
            f"[ProgressTracker] get_process: key={ptype} value={detail.get('value')} enable={detail.get('enable')}"
        )
        return detail
