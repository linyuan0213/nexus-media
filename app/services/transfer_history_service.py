from math import floor

from app.core.module_config import ModuleConf
from app.schemas.media import TransferHistoryPageDTO, UnknownListPageDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer


class TransferHistoryService:
    """
    转移历史业务服务
    """

    def __init__(self, filetransfer: FileTransfer | None = None):
        self._filetransfer = filetransfer or FileTransfer()

    def get_transfer_history_page(self, search_str, page, page_num) -> TransferHistoryPageDTO:
        """分页查询转移历史"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        total_count, historys = self._filetransfer.get_transfer_history(search_str, page, page_num)
        historys_list = []
        for history in historys:
            history = history.as_dict()
            sync_mode = history.get("MODE")
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            history.update({"SYNC_MODE": sync_mode, "RMT_MODE": rmt_mode})
            historys_list.append(history)
        total_page = floor(total_count / page_num) + 1
        return TransferHistoryPageDTO(
            total=total_count, result=historys_list, total_page=total_page,
            page_num=page_num, current_page=page
        )

    def get_transfer_statistics(self, days=90) -> dict:
        """获取转移统计"""
        Labels = []
        MovieNums = []
        TvNums = []
        AnimeNums = []
        for statistic in self._filetransfer.get_transfer_statistics(days):
            if not statistic[2]:
                continue
            if statistic[1] not in Labels:
                Labels.append(statistic[1])
            if statistic[0] == "电影":
                MovieNums.append(statistic[2])
                TvNums.append(0)
                AnimeNums.append(0)
            elif statistic[0] == "电视剧":
                TvNums.append(statistic[2])
                MovieNums.append(0)
                AnimeNums.append(0)
            else:
                AnimeNums.append(statistic[2])
                MovieNums.append(0)
                TvNums.append(0)
        return {"Labels": Labels, "MovieNums": MovieNums,
                "TvNums": TvNums, "AnimeNums": AnimeNums}

    def get_unknown_list(self) -> list[dict]:
        """获取未识别记录列表"""
        Items = []
        Records = self._filetransfer.get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID, "path": path, "to": path_to, "name": path,
                "sync_mode": sync_mode, "rmt_mode": rmt_mode,
            })
        return Items

    def get_unknown_list_by_page(self, search_str, page, page_num) -> UnknownListPageDTO:
        """分页查询未识别记录"""
        if not page_num:
            page_num = 30
        if not page:
            page = 1
        else:
            page = int(page)
        total_count, Records = self._filetransfer.get_transfer_unknown_paths_by_page(
            search_str, page, page_num)
        Items = []
        for rec in Records:
            if not rec.PATH:
                continue
            path = rec.PATH.replace("\\", "/") if rec.PATH else ""
            path_to = rec.DEST.replace("\\", "/") if rec.DEST else ""
            sync_mode = rec.MODE or ""
            rmt_mode = ModuleConf.get_dictenum_key(ModuleConf.RMT_MODES, sync_mode) if sync_mode else ""
            Items.append({
                "id": rec.ID, "path": path, "to": path_to, "name": path,
                "sync_mode": sync_mode, "rmt_mode": rmt_mode,
            })
        total_page = floor(total_count / page_num) + 1
        return UnknownListPageDTO(
            total=total_count, items=Items, total_page=total_page,
            page_num=page_num, current_page=page
        )

    def re_identify_unknown(self) -> int:
        """重新识别所有未识别记录"""
        from app.services.sync_service import SyncService
        ItemIds = []
        Records = self._filetransfer.get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            ItemIds.append(rec.ID)
        if ItemIds:
            SyncService().re_identify_items(flag="unidentification", ids=ItemIds)
        return len(ItemIds)

    def clear_history(self):
        """清空识别记录"""
        self._filetransfer.delete_transfer()
        self._filetransfer.truncate_transfer_blacklist()
