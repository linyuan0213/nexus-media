# Compatibility shim: re-exports moved to app.services.rss package
from app.services.rss_automation import RssParserEngine, RssTaskService

__all__ = ["RssParserEngine", "RssTaskService"]
