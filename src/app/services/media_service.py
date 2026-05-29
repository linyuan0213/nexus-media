"""
MediaService - 媒体管理业务层
将 web/controllers/media.py 中的复杂业务逻辑下沉到可独立测试的 Service。
"""

from app.services.media_file_service import MediaFileService
from app.services.media_info_service import MediaInfoService
from app.services.media_library_service import MediaLibraryService
from app.services.media_recommendation_service import MediaRecommendationService
from app.services.search_result_service import SearchResultService
from app.services.transfer_history_service import TransferHistoryService

__all__ = [
    "MediaInfoService",
    "MediaRecommendationService",
    "SearchResultService",
    "MediaLibraryService",
    "TransferHistoryService",
    "MediaFileService",
]
