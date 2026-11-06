"""统一媒体身份解析服务（兼容导出）.

实现位于仓储层 `app.db.repositories.identity_resolver`，避免 Repository 反向依赖
services。业务代码保留原有导入路径即可。
"""

from app.db.repositories.identity_resolver import IdentityResolver, ResolvedIdentity

__all__ = ["IdentityResolver", "ResolvedIdentity"]
