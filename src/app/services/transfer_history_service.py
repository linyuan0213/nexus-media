from math import floor

from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.di import container
from app.schemas.media import TransferHistoryPageDTO, UnknownListPageDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.sync_service import SyncService
from app.utils.types import MediaType


class TransferHistoryService:
    """
    转移历史业务服务
    """

    def __init__(self, filetransfer: FileTransfer | None = None, sync_service: SyncService | None = None):
        self._filetransfer = filetransfer or container.filetransfer_service()
        self._sync_service = sync_service or container.sync_service()

    def get_transfer_history_page(self, search_str, page, page_num) -> TransferHistoryPageDTO:
        """分页查询转移历史"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        result = self._filetransfer.get_transfer_history(search_str, page, page_num)
        if result is None:
            total_count, historys = 0, []
        else:
            total_count, historys = result
        historys_list = []
        for history in historys:
            history = history.as_dict()
            sync_mode = history.get("MODE")
            rmt_mode = sync_mode or ""
            history.update({"SYNC_MODE": sync_mode, "RMT_MODE": rmt_mode})
            historys_list.append(history)
        total_page = floor(total_count / page_num) + 1
        return TransferHistoryPageDTO(
            total=total_count, result=historys_list, total_page=total_page, page_num=page_num, current_page=page
        )

    def get_transfer_statistics(self, days=90) -> dict:
        """获取转移统计"""
        labels = []
        movie_nums = []
        tv_nums = []
        anime_nums = []
        for statistic in self._filetransfer.get_transfer_statistics(days) or []:
            if not statistic[2]:
                continue
            if statistic[1] not in labels:
                labels.append(statistic[1])
            parsed = MediaType.from_string(statistic[0])
            if parsed == MediaType.MOVIE:
                movie_nums.append(statistic[2])
                tv_nums.append(0)
                anime_nums.append(0)
            elif parsed == MediaType.TV:
                tv_nums.append(statistic[2])
                movie_nums.append(0)
                anime_nums.append(0)
            elif parsed == MediaType.ANIME:
                anime_nums.append(statistic[2])
                movie_nums.append(0)
                tv_nums.append(0)
        return {"Labels": labels, "MovieNums": movie_nums, "TvNums": tv_nums, "AnimeNums": anime_nums}

    def get_unknown_list(self) -> list[dict]:
        """获取未识别记录列表"""
        items = []
        records = self._filetransfer.get_transfer_unknown_paths() or []
        for rec in records:
            rec_path = str(rec.PATH or "")
            if not rec_path:
                continue
            path = rec_path.replace("\\", "/")
            path_to = str(rec.DEST or "").replace("\\", "/")
            sync_mode = str(rec.MODE or "")
            rmt_mode = sync_mode
            dst_backend = self._filetransfer.get_sync_backend_by_dest(path_to)
            items.append(
                {
                    "id": rec.ID,
                    "path": path,
                    "to": path_to,
                    "name": path,
                    "sync_mode": sync_mode,
                    "rmt_mode": rmt_mode,
                    "dst_backend": dst_backend,
                }
            )
        return items

    def get_unknown_list_by_page(self, search_str, page, page_num) -> UnknownListPageDTO:
        """分页查询未识别记录"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        result2 = self._filetransfer.get_transfer_unknown_paths_by_page(search_str, page, page_num)
        if result2 is None:
            total_count, records = 0, []
        else:
            total_count, records = result2
        items = []
        for rec in records:
            rec_path = str(rec.PATH or "")
            if not rec_path:
                continue
            path = rec_path.replace("\\", "/")
            path_to = str(rec.DEST or "").replace("\\", "/")
            sync_mode = str(rec.MODE or "")
            rmt_mode = sync_mode
            dst_backend = self._filetransfer.get_sync_backend_by_dest(path_to)
            items.append(
                {
                    "id": rec.ID,
                    "path": path,
                    "to": path_to,
                    "name": path,
                    "sync_mode": sync_mode,
                    "rmt_mode": rmt_mode,
                    "dst_backend": dst_backend,
                }
            )
        total_page = floor(total_count / page_num) + 1
        return UnknownListPageDTO(
            total=total_count, items=items, total_page=total_page, page_num=page_num, current_page=page
        )

    def re_identify_unknown(self) -> int:
        """重新识别所有未识别记录"""
        item_ids = []
        records = self._filetransfer.get_transfer_unknown_paths() or []
        for rec in records:
            rec_path = str(rec.PATH or "")
            if not rec_path:
                continue
            item_ids.append(rec.ID)
        if item_ids:
            self._sync_service.re_identify_items(flag="unidentification", ids=item_ids)
        return len(item_ids)

    def clear_history(self):
        """清空识别记录"""
        self._filetransfer.delete_transfer()
        self._filetransfer.truncate_transfer_blacklist()
