"""MediaExistenceChecker - 媒体文件存在性检查."""

import os

from app.core.constants import RMT_FAVTYPE, RMT_MEDIAEXT
from app.utils import PathUtils
from app.utils.types import MediaType


class MediaExistenceChecker:
    """负责检查媒体文件是否已存在于目标目录（支持本地和远程后端）."""

    def __init__(self, path_resolver):
        self._path_resolver = path_resolver

    def is_media_exists(self, media_dest, media, dst_backend=None):
        """
        判断媒体文件是否已存在.
        :return: (dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path)
        """
        backend = dst_backend

        def _exists(path: str) -> bool:
            if backend is not None:
                return backend.exists(path)
            return os.path.exists(path)

        dir_exist_flag = False
        file_exist_flag = False
        ret_dir_path = None
        ret_file_path = None

        if media.type == MediaType.MOVIE:
            dir_name, file_name = self._path_resolver.get_movie_dest_path(media)
            file_path = os.path.join(media_dest, dir_name)
            if self._path_resolver.movie_category_flag:
                file_path = os.path.join(media_dest, media.category, dir_name)
                for m_type in [RMT_FAVTYPE, media.category]:
                    type_path = os.path.join(media_dest, m_type, dir_name)
                    if _exists(type_path):
                        file_path = type_path
                        break
            ret_dir_path = file_path
            if _exists(file_path):
                dir_exist_flag = True
            file_dest = os.path.join(file_path, file_name)
            ret_file_path = file_dest
            for ext in RMT_MEDIAEXT:
                ext_dest = f"{file_dest}{ext}"
                if _exists(ext_dest):
                    file_exist_flag = True
                    ret_file_path = ext_dest
                    break
        else:
            dir_name, season_name, file_name = self._path_resolver.get_tv_dest_path(media)
            if (media.type == MediaType.TV and self._path_resolver.tv_category_flag) or (
                media.type == MediaType.ANIME and self._path_resolver.anime_category_flag
            ):
                media_path = os.path.join(media_dest, media.category, dir_name)
            else:
                media_path = os.path.join(media_dest, dir_name)
            if media.get_season_list():
                season_dir = os.path.join(media_path, season_name)
                ret_dir_path = season_dir
                if _exists(season_dir):
                    dir_exist_flag = True
                episodes = media.get_episode_list()
                if episodes:
                    file_path = os.path.join(season_dir, file_name)
                    ret_file_path = file_path
                    for ext in RMT_MEDIAEXT:
                        ext_dest = f"{file_path}{ext}"
                        if _exists(ext_dest):
                            file_exist_flag = True
                            ret_file_path = ext_dest
                            break
        return dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path

    def get_no_exists_medias(self, meta_info_obj, meta_info_fn, season=None, total_num=None):
        """
        根据媒体库目录结构，判断媒体是否存在.
        :return: 电影返回已存在的电影清单，剧集返回不存在的集的清单.
        """
        if meta_info_obj.type == MediaType.MOVIE:
            dir_name, _ = self._path_resolver.get_movie_dest_path(meta_info_obj)
            for dest_path in self._path_resolver.movie_path:
                fav_path = os.path.join(dest_path, RMT_FAVTYPE, dir_name)
                fav_files = PathUtils.get_dir_files(fav_path, RMT_MEDIAEXT)
                if self._path_resolver.movie_category_flag:
                    dest_path = os.path.join(dest_path, meta_info_obj.category, dir_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name)
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                if len(files) > 0 or len(fav_files) > 0:
                    return [{"title": meta_info_obj.title, "year": meta_info_obj.year}]
            return []
        else:
            dir_name, season_name, _ = self._path_resolver.get_tv_dest_path(meta_info_obj)
            if not season or not total_num:
                return []
            if meta_info_obj.type == MediaType.ANIME:
                dest_paths = self._path_resolver.anime_path
                category_flag = self._path_resolver.anime_category_flag
            else:
                dest_paths = self._path_resolver.tv_path
                category_flag = self._path_resolver.tv_category_flag
            total_episodes = list(range(1, total_num + 1))
            exists_episodes = []
            for dest_path in dest_paths:
                if category_flag:
                    dest_path = os.path.join(dest_path, meta_info_obj.category, dir_name, season_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name, season_name)
                if not os.path.exists(dest_path):
                    continue
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                for file in files:
                    file_meta_info = meta_info_fn(title=os.path.basename(file))
                    if not file_meta_info.get_season_list() or not file_meta_info.get_episode_list():
                        continue
                    if file_meta_info.get_name() != meta_info_obj.title:
                        continue
                    if not file_meta_info.is_in_season(season):
                        continue
                    exists_episodes = list(set(exists_episodes).union(set(file_meta_info.get_episode_list())))
            return list(set(total_episodes).difference(set(exists_episodes)))
