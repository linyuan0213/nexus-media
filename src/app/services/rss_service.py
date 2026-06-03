# Compatibility shim: re-exports moved to app.services.rss package
from app.services.rss_automation.parser import RssParserEngine
from app.services.rss_automation.task_service import RssTaskService

__all__ = ["RssParserEngine", "RssTaskService"]
