"""
全局装饰器：登录校验、参数解析、异常处理
"""
from functools import wraps
from flask import request
from flask_login import current_user
from web.core.response import fail


def action_login_check(func):
    """
    Action安全认证装饰器
    """
    @wraps(func)
    def login_check(*args, **kwargs):
        if not current_user.is_authenticated:
            return fail(code=-1, msg="用户未登录")
        return func(*args, **kwargs)
    return login_check


def parse_json_data(func):
    """
    自动提取 request.get_json() 中的 data 字段作为视图函数第一个位置参数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 若已被直接调用并传入位置参数，则直接透传，避免重复注入 data
        if args:
            return func(*args, **kwargs)
        payload = request.get_json(silent=True) or {}
        data = payload.get("data") if "data" in payload else payload
        return func(data, *args, **kwargs)
    return wrapper
