"""内容画像/元数据 provider 权限判断."""

from app.media.metadata.registry import registry as metadata_registry
from app.schemas.auth import UserContext

PRIVATE_METADATA_PERMISSION = "metadata:private:view"
PUBLIC_PROFILES = frozenset({"", "default", "anime"})


def can_use_private_metadata(
    user: UserContext,
    *,
    provider: str | None = None,
    metadata_ref: str | None = None,
    content_profile: str | None = None,
) -> bool:
    """判断用户是否可使用指定画像/provider；公共画像和公共 provider 始终允许。"""
    permissions = set(getattr(user, "permissions", []) or [])
    if getattr(user, "is_superadmin", False) or PRIVATE_METADATA_PERMISSION in permissions:
        return True
    profile = str(content_profile or "").strip()
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        ref = str(metadata_ref or "")
        if ":" in ref:
            provider_key = ref.split(":", 1)[0].strip().lower()
    descriptor = getattr(metadata_registry.get_provider(provider_key), "descriptor", None) if provider_key else None
    private_provider = getattr(descriptor, "visibility", "public") == "private"
    return not private_provider and profile in PUBLIC_PROFILES
