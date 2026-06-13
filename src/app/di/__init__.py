"""app.di — 依赖注入模块."""

from .builders.context_builder import build_app_context
from .context import AppContext

__all__ = ["AppContext", "build_app_context"]
