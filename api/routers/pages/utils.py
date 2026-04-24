"""
Pages Router Utils - 共享工具和模板过滤器
"""
import os
import hashlib
from fastapi.templating import Jinja2Templates

# 模板目录与 Flask 共用
_template_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "web", "templates"
)
templates = Jinja2Templates(directory=_template_dir)


def parse_brush_rule_string(rules: dict) -> str:
    """解析刷流规则为字符串"""
    if not rules:
        return ""
    result = []
    for key, value in rules.items():
        if value:
            result.append(f"{key}: {value}")
    return "<br>".join(result) if result else ""


def str_filesize(size: int) -> str:
    """格式化文件大小"""
    if not size:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"


def md5_hash(text) -> str:
    """MD5 HASH"""
    if text is None:
        return ""
    return hashlib.md5(str(text).encode()).hexdigest()


def register_template_filters(app):
    """注册模板过滤器到 FastAPI 的 Jinja2 环境"""
    env = templates.env
    env.filters['b64encode'] = lambda s: __import__('base64').b64encode(s.encode()).decode()
    env.filters['split'] = lambda string, char, pos: string.split(char)[int(pos)]
    env.filters['brush_rule_string'] = parse_brush_rule_string
    env.filters['str_filesize'] = str_filesize
    env.filters['hash'] = md5_hash
    # 兼容模板中 request.host 的用法（Flask → FastAPI）
    env.filters['host'] = lambda req: req.url.hostname if hasattr(req, 'url') else ''
