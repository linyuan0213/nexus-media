"""会话键工具：把含 URL 的会话标识规范化为 URL 安全 id（路径段使用）."""

import re


def to_session_id(key: str) -> str:
    """规范化为 URL 安全会话 id.

    只保留 [A-Za-z0-9_-]，其余（`/`、`:`、`.` 等）替换为 `_`：
    URL 型会话键含 `/`、`:` 等字符，编码后仍可能不被 nexus-chrome 路由正确解码，
    因此统一为纯 ASCII 安全 id（仅作标识，无需可逆）。
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", key or "")
