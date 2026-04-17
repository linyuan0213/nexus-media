"""
全局装饰器：登录校验、参数解析、异常处理
"""
from functools import wraps
from flask import request
from flask_login import current_user
from web.core.response import fail
from web.security import identify, TokenCache, generate_access_token
from config import Config


def any_auth(func):
    """
    统一认证装饰器：同时兼容 Session 登录、Token(Bearer)、API Key。
    让 Web 前端、APIv1 Client、APIv1 Api 都能无差别调用同一套 Controller。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 1) Session 认证（Web 前端）
        if current_user.is_authenticated:
            return func(*args, **kwargs)

        # 2) Token 认证（APIv1 ClientResource / Bearer）
        auth_header = request.headers.get("Authorization")
        if auth_header:
            latest_token = TokenCache.get(auth_header)
            if latest_token:
                flag, username = identify(latest_token)
                if username:
                    if not flag:
                        TokenCache.set(auth_header, generate_access_token(username))
                    return func(*args, **kwargs)

        # 3) API Key 认证（APIv1 ApiResource / 外部调用）
        api_key = Config().get_config("security").get("api_key")
        if auth_header:
            auth_val = str(auth_header).split()[-1]
            if auth_val == api_key:
                return func(*args, **kwargs)
        query_key = request.args.get("apikey")
        if query_key and query_key == api_key:
            return func(*args, **kwargs)

        return fail(code=401, msg="安全认证未通过，请检查登录状态、Token 或 ApiKey")
    return wrapper


# 向后兼容别名：所有 Controller 已统一迁移到 @any_auth
action_login_check = any_auth


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
