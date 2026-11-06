"""合成策略与预设（兼容导出）.

策略本身属于 domain，media 层保留原导入路径。
"""

from app.domain.metadata_policy import (
    ANCHOR_POLICY,
    DEFAULT_POLICY_KEY,
    FieldRule,
    MergeMode,
    MetadataPolicy,
    get_preset,
    resolve_policy,
)

__all__ = [
    "ANCHOR_POLICY",
    "DEFAULT_POLICY_KEY",
    "FieldRule",
    "MetadataPolicy",
    "MergeMode",
    "get_preset",
    "resolve_policy",
]
