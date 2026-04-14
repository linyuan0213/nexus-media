from web.actions._base import WebActionBase
from web.actions._system import WebActionSystemMixin
from web.actions._media import WebActionMediaMixin
from web.actions._site import WebActionSiteMixin
from web.actions._download import WebActionDownloadMixin
from web.actions._rss import WebActionRssMixin
from web.actions._userrss import WebActionUserrssMixin
from web.actions._filter import WebActionFilterMixin
from web.actions._words import WebActionWordsMixin
from web.actions._brush import WebActionBrushMixin
from web.actions._sync import WebActionSyncMixin
from web.actions._plugin import WebActionPluginMixin
from web.actions._rbac import WebActionRbacMixin
from web.actions._scheduler import WebActionSchedulerMixin


class WebAction(
    WebActionSchedulerMixin,
    WebActionPluginMixin,
    WebActionRbacMixin,
    WebActionSyncMixin,
    WebActionBrushMixin,
    WebActionWordsMixin,
    WebActionFilterMixin,
    WebActionUserrssMixin,
    WebActionRssMixin,
    WebActionDownloadMixin,
    WebActionSiteMixin,
    WebActionMediaMixin,
    WebActionSystemMixin,
    WebActionBase,
):
    pass
