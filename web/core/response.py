"""
统一 Web 响应格式工具
"""
from typing import Any, Dict


class WebResponse:
    """统一成功/失败响应封装"""

    @staticmethod
    def success(data: Any = None, **kwargs) -> Dict[str, Any]:
        result = {"code": 0}
        if data is not None:
            result["data"] = data
        result.update(kwargs)
        return result

    @staticmethod
    def fail(code: int = 1, msg: str = "", **kwargs) -> Dict[str, Any]:
        result = {"code": code, "msg": msg}
        result.update(kwargs)
        return result


# 顶层便捷函数，供装饰器及其他模块直接使用
def success(data: Any = None, **kwargs) -> Dict[str, Any]:
    return WebResponse.success(data=data, **kwargs)


def fail(code: int = 1, msg: str = "", **kwargs) -> Dict[str, Any]:
    return WebResponse.fail(code=code, msg=msg, **kwargs)
