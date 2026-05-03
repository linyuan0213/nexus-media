"""
Search Repository
Handles search result related database operations.
"""
import json
from typing import List, Optional

from sqlalchemy import func

from app.db import DbPersist
from app.db.models import SEARCHRESULTINFO
from app.db.repositories.base_repository import BaseRepository
from app.utils import StringUtils
from app.utils.types import MediaType


class SearchRepository(BaseRepository):
    """
    搜索结果仓储
    处理搜索结果的数据库操作
    """

    @DbPersist(BaseRepository._db)
    def insert_search_results(self, media_items: list, title=None, ident_flag=True):
        """
        将返回信息插入数据库
        使用批量插入映射以提高性能
        
        Args:
            media_items: 媒体信息列表
            title: 标题（用于非识别模式）
            ident_flag: 是否已识别标识
        """
        if not media_items:
            return

        mappings = []
        for media_item in media_items:
            if media_item.type == MediaType.TV:
                mtype = "TV"
            elif media_item.type == MediaType.MOVIE:
                mtype = "MOV"
            else:
                mtype = "ANI"

            # 截断超长 ENCLOSURE 防止数据库错误（8192 字节上限）
            enclosure = media_item.enclosure
            if enclosure and len(enclosure) > 8192:
                enclosure = enclosure[:8192]

            mappings.append({
                'TORRENT_NAME': media_item.org_string,
                'ENCLOSURE': enclosure,
                'DESCRIPTION': media_item.description,
                'TYPE': mtype if ident_flag else '',
                'TITLE': media_item.title if ident_flag else title,
                'YEAR': media_item.year if ident_flag else '',
                'SEASON': media_item.get_season_string() if ident_flag else '',
                'EPISODE': media_item.get_episode_string() if ident_flag else '',
                'ES_STRING': media_item.get_season_episode_string() if ident_flag else '',
                'VOTE': media_item.vote_average or "0",
                'IMAGE': media_item.get_backdrop_image(default=False, original=True),
                'POSTER': media_item.get_poster_image(),
                'TMDBID': media_item.tmdb_id,
                'OVERVIEW': media_item.overview,
                'RES_TYPE': json.dumps({
                    "respix": media_item.resource_pix,
                    "restype": media_item.resource_type,
                    "reseffect": media_item.resource_effect,
                    "video_encode": media_item.video_encode
                }),
                'RES_ORDER': media_item.res_order,
                'SIZE': int(media_item.size or 0),
                'SEEDERS': int(media_item.seeders) if media_item.seeders and str(media_item.seeders).strip().lstrip('-+').isdigit() else 0,
                'PEERS': int(media_item.peers) if media_item.peers and str(media_item.peers).strip().lstrip('-+').isdigit() else 0,
                'SITE': media_item.site,
                'SITE_ORDER': media_item.site_order,
                'PAGEURL': media_item.page_url,
                'OTHERINFO': media_item.resource_team,
                'UPLOAD_VOLUME_FACTOR': media_item.upload_volume_factor,
                'DOWNLOAD_VOLUME_FACTOR': media_item.download_volume_factor,
                'NOTE': '|'.join(media_item.labels) if isinstance(media_item.labels, list) else (media_item.labels or '')
            })

        self._db.bulk_insert_mappings(SEARCHRESULTINFO, mappings, batch_size=500)

    def get_search_result_by_id(self, dl_id):
        """
        根据ID从数据库中查询搜索结果的一条记录
        
        Args:
            dl_id: 下载ID
            
        Returns:
            搜索结果记录列表
        """
        return self._db.query(SEARCHRESULTINFO).filter(SEARCHRESULTINFO.ID == dl_id).all()

    def get_search_results(self):
        """
        查询搜索结果的所有记录
        
        Returns:
            所有搜索结果记录
        """
        return self._db.query(SEARCHRESULTINFO).all()

    @DbPersist(BaseRepository._db)
    def delete_all_search_torrents(self):
        """
        删除所有搜索的记录
        """
        self._db.query(SEARCHRESULTINFO).delete()
