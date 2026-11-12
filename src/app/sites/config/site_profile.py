"""站点 API profile 选择与用户配置合并."""

from typing import Any


def _explicit_profile_token(user_config: dict, profile_name: str, key: str) -> bool:
    """显式 token_key 优先只接受该 profile 的 NOTE.api_credentials.

    避免把站点顶层 BEARER_TOKEN（通常是另一套 API 的 token）误当成
    SPA profile 的 JWT。
    """
    note = user_config.get("note") or {}
    credentials = note.get("api_credentials") or user_config.get("api_credentials") or {}
    if profile_name:
        item = credentials.get(profile_name) if isinstance(credentials, dict) else None
        return bool(item.get(key)) if isinstance(item, dict) else False
    return bool(user_config.get(key))


def _profile_ready(api: Any, user_config: dict, profile_name: str = "") -> bool:
    """判断 profile 是否具备最小认证条件，避免选中缺凭据的高优先级 profile."""
    auth = getattr(api, "auth", {}) or {}
    auth_type = str(auth.get("type") or "")
    if auth_type == "api_key":
        explicit = str(auth.get("token_key") or "").strip()
        if explicit:
            return _explicit_profile_token(user_config, profile_name, explicit)
        return bool(user_config.get("api_key") or user_config.get("cookie"))
    if auth_type == "bearer":
        explicit = str(auth.get("token_key") or "").strip()
        if explicit:
            return _explicit_profile_token(user_config, profile_name, explicit)
        return bool(user_config.get("bearer_token") or user_config.get("api_key") or user_config.get("cookie"))
    if auth_type in {"cookie", "csrf"}:
        return bool(user_config.get("cookie") or user_config.get("bearer_token"))
    return True


def api_profile_candidates(
    site: Any,
    user_config: dict,
    capability: str = "search",
) -> list[tuple[str, Any, dict]]:
    """按用户选择/capability 顺序返回可用 profile；无 profiles 时返回旧 api."""
    api = getattr(site, "api", None)
    if not api:
        return []
    profiles = getattr(api, "profiles", None) or {}
    if not profiles:
        return [("", api, dict(user_config))]

    note = user_config.get("note") or {}
    selected = str(user_config.get("api_profile") or note.get("api_profile") or "").strip()
    names: list[str] = []
    if selected:
        names.append(selected)
    for name in (getattr(api, "capabilities", None) or {}).get(capability, []):
        names.append(str(name))
    default = str(getattr(api, "default_profile", "") or "").strip()
    if default:
        names.append(default)
    names.extend(str(name) for name in profiles)

    seen: set[str] = set()
    ready: list[tuple[str, Any, dict]] = []
    fallback: list[tuple[str, Any, dict]] = []
    for name in names:
        if name in seen or name not in profiles:
            continue
        seen.add(name)
        profile_config = profile_user_config(user_config, name)
        item = (name, profiles[name], profile_config)
        if _profile_ready(profiles[name], profile_config, name):
            ready.append(item)
        else:
            fallback.append(item)
    return ready or fallback


def resolve_api_profile(site: Any, user_config: dict, capability: str = "search") -> tuple[str, Any] | None:
    """选择一个 API profile；没有 profiles 时返回旧 site.api。"""
    api = getattr(site, "api", None)
    if not api:
        return None
    profiles = getattr(api, "profiles", None) or {}
    if not profiles:
        return "", api

    note = user_config.get("note") or {}
    selected = str(user_config.get("api_profile") or note.get("api_profile") or "").strip()

    def ready(name: str) -> bool:
        return name in profiles and _profile_ready(
            profiles[name],
            profile_user_config(user_config, name),
            name,
        )

    if capability == "search" and selected and ready(selected):
        return selected, profiles[selected]

    for name in (getattr(api, "capabilities", None) or {}).get(capability, []):
        if ready(str(name)):
            return str(name), profiles[str(name)]

    if selected and ready(selected):
        return selected, profiles[selected]

    default = str(getattr(api, "default_profile", "") or "").strip()
    if ready(default):
        return default, profiles[default]
    if capability == "search":
        for name in profiles:
            if ready(str(name)):
                return str(name), profiles[name]
    name = default if default in profiles else next(iter(profiles))
    return str(name), profiles[name]


def profile_user_config(user_config: dict, profile_name: str) -> dict:
    """合并 NOTE.api_credentials[profile] 到用户配置，供认证复用."""
    merged = dict(user_config or {})
    if not profile_name:
        return merged
    note = merged.get("note") or {}
    credentials = note.get("api_credentials") or merged.get("api_credentials") or {}
    if isinstance(credentials, dict):
        extra = credentials.get(profile_name)
        if isinstance(extra, dict):
            merged.update(extra)
    merged["api_profile"] = profile_name
    return merged
