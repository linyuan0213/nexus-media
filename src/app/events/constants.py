"""
事件类型常量

所有事件类型字符串在此集中定义，与 HookSystem 兼容。
命名规范：domain.action，用下划线分隔多词
"""

# 媒体相关
MEDIA_TRANSFER_FINISHED = "media.transfer_finished"
MEDIA_EPISODE_TRANSFERRED = "media.episode_transferred"
MEDIA_LIBRARY_SYNCED = "media.library_synced"
MEDIA_SCRAPED = "media.scraped"
MEDIA_SOURCE_DELETED = "media.source_deleted"
MEDIA_DOUBAN_SYNC = "media.douban_sync"

# 下载相关
DOWNLOAD_STARTED = "download.started"
DOWNLOAD_COMPLETED = "download.completed"
DOWNLOAD_FAILED = "download.failed"

# 订阅相关
SUBSCRIBE_ADD = "subscribe.add"
SUBSCRIBE_FINISHED = "subscribe.finished"

# 搜索相关
SEARCH_START = "search.start"

# 转移相关
TRANSFER_FAIL = "transfer.fail"
LIBRARY_FILE_DELETED = "library.file_deleted"

# 站点相关
SITE_COOKIE_SYNC = "site.cookie_sync"
SITE_LOCAL_STORAGE_SYNC = "site.local_storage_sync"
SITE_SIGNIN = "site.signin"

# Webhook
WEBHOOK_EMBY = "webhook.emby"
WEBHOOK_JELLYFIN = "webhook.jellyfin"
WEBHOOK_PLEX = "webhook.plex"

# 其他
SUBTITLE_DOWNLOAD = "subtitle.download"
MESSAGE_INCOMING = "message.incoming"
WEWORK_LOGIN = "wework.login"
PLUGIN_RELOAD = "plugin.reload"
AUTOSEED_START = "autoseed.start"
