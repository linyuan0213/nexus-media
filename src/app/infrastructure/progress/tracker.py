from enum import Enum

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

    def end(self, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        if not self._process_detail.get(ptype):
            return
        self._process_detail[ptype]["value"] = 100
        self._process_detail[ptype]["text"] = "处理完成"
        self._process_detail[ptype]["enable"] = False

    def update(self, value=None, text=None, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        if not self._process_detail.get(ptype, {}).get("enable"):
            return
        if value:
            self._process_detail[ptype]["value"] = value
        if text:
            self._process_detail[ptype]["text"] = text

    def get_process(self, ptype=ProgressKey.Search):
        if isinstance(ptype, Enum):
            ptype = ptype.value
        return self._process_detail.get(ptype)
