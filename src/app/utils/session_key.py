"""会话键工具：把含 URL 的会话标识规范化为 URL 安全 id（路径段使用）."""

import hashlib
import re

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def to_session_id(key: str) -> str:
    """规范化为 URL 安全且无碰撞的会话 id.

    已经是 URL 安全短 id 的（如手工 session key）保持不变；URL、域名、
    中文站名等可能因字符替换而碰撞，统一使用内容哈希。旧版 ``_____`` 型
    规范化 id 因此不再命中，首次会创建新会话，但不会跨站/跨用户复用 Cookie。
    """
    text = str(key or "")
    if _SAFE_ID.fullmatch(text):
        return text
    return f"h_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]}"
