"""渠道身份绑定服务（ADR-021 5.8）.

- 交互渠道（TG/企微/Slack 等）：Web 生成一次性绑定码 → IM 发送 /bind <code> 完成绑定
- 纯推送渠道（Bark/Ntfy 等）：Web 端直接登记推送 Key
- 入站消息按绑定解析系统用户身份，未绑定拒绝交互
"""

import secrets

import log
from app.db.repositories.channel_binding_repository import ChannelBindingRepository
from app.infrastructure.cache_system import TokenCache
from app.schemas.auth import UserContext

_BIND_CODE_PREFIX = "channel_bind:"
_BIND_CODE_TTL = 600  # 10 分钟
_BIND_MAX_ATTEMPTS = 5  # 防爆破：失败 5 次失效

# 支持入站绑定的交互渠道
INTERACTIVE_CHANNELS = {"telegram", "wechat", "slack", "synologychat"}


class ChannelBindingService:
    """渠道身份绑定服务"""

    def __init__(self, repo: ChannelBindingRepository, rbac_service):
        self._repo = repo
        self._rbac_service = rbac_service

    # ---------- 绑定码（交互渠道） ----------

    def create_bind_code(self, user_id: int) -> str:
        """生成 6 位一次性绑定码"""
        code = f"{secrets.randbelow(1000000):06d}"
        TokenCache.set(_BIND_CODE_PREFIX + code, {"user_id": user_id, "attempts": 0}, ttl=_BIND_CODE_TTL)
        return code

    def bind_by_code(self, code: str, channel: str, channel_user_id: str) -> tuple[bool, str]:
        """用绑定码完成绑定（IM 侧 /bind 命令调用）"""
        if not channel or not channel_user_id:
            return False, "缺少渠道身份"
        key = _BIND_CODE_PREFIX + (code or "").strip()
        payload = TokenCache.get(key)
        if not payload:
            return False, "绑定码无效或已过期"
        attempts = int(payload.get("attempts", 0)) + 1
        if attempts >= _BIND_MAX_ATTEMPTS:
            TokenCache.delete(key)
            return False, "尝试次数过多，绑定码已失效"
        payload["attempts"] = attempts
        TokenCache.set(key, payload, ttl=_BIND_CODE_TTL)

        user_id = int(payload["user_id"])
        user = self._rbac_service.get_user_by_id(user_id)
        if not user or getattr(user, "STATUS", 1) != 1:
            TokenCache.delete(key)
            return False, "用户不存在或已禁用"

        existing = self._repo.get_binding(channel, channel_user_id)
        if existing and existing.USER_ID != user_id:
            return False, "该渠道账号已绑定其他用户"

        self._repo.bind(user_id, channel, channel_user_id)
        TokenCache.delete(key)
        log.info(f"[ChannelBinding] 用户 {user_id} 绑定 {channel}:{channel_user_id}")
        return True, f"绑定成功：{getattr(user, 'USERNAME', user_id)}"

    # ---------- 手动登记（推送渠道） ----------

    def bind_direct(self, user_id: int, channel: str, channel_user_id: str) -> tuple[bool, str]:
        """Web 端直接登记推送目标（Bark Key 等）"""
        if not channel or not channel_user_id:
            return False, "缺少渠道身份"
        existing = self._repo.get_binding(channel, channel_user_id)
        if existing and existing.USER_ID != user_id:
            return False, "该渠道目标已被其他用户绑定"
        self._repo.bind(user_id, channel, channel_user_id)
        return True, "绑定成功"

    # ---------- 查询/解绑 ----------

    def list_bindings(self, user_id: int) -> list[dict]:
        return [row.to_dict() for row in self._repo.list_by_user(user_id)]

    def unbind(self, user_id: int, channel: str, channel_user_id: str) -> bool:
        return self._repo.unbind(user_id, channel, channel_user_id)

    def unbind_by_id(self, binding_id: int) -> bool:
        return self._repo.unbind_by_id(binding_id)

    # ---------- 入站身份解析 ----------

    def resolve_user(self, channel: str, channel_user_id: str) -> UserContext | None:
        """渠道身份 → 系统用户上下文（含实时权限/角色快照），未绑定返回 None"""
        binding = self._repo.get_binding(channel, str(channel_user_id or ""))
        if not binding:
            return None
        user = self._rbac_service.get_user_by_id(binding.USER_ID)
        if not user or getattr(user, "STATUS", 1) != 1:
            return None
        snapshot = self._rbac_service.get_user_snapshot(binding.USER_ID)
        return UserContext(
            user_id=binding.USER_ID,
            username=getattr(user, "USERNAME", str(binding.USER_ID)),
            nickname=getattr(user, "NICKNAME", None),
            level=getattr(user, "LEVEL", 0) or 0,
            permissions=sorted(snapshot.permissions),
            role_codes=sorted(snapshot.role_codes),
        )
