"""会话键工具：把含 URL 的会话标识规范化为 URL 安全 id（路径段使用）."""

import re


def to_session_id(key: str) -> str:
    """规范化为 URL 安全会话 id.

    会话键可能包含站点 URL（如 https://a.me），其中的 `/` 等字符无法作为
    单个路径段传给 nexus-chrome；统一替换为 `_`（仅作标识，无需可逆）。
    """
    return re.sub(r"[^A-Za-z0-9_.:\-]", "_", key or "")
