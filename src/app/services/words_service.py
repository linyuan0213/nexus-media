"""
WordsService - 自定义识别词服务
合并原 WordsHelper 的处理逻辑和数据库操作。
"""

import base64
import json
import time


from app.core.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError, ValidationError
from app.domain.entities.word import CustomWordEntity
from app.domain.mediatypes import MediaType
from app.domain.word_processor import process_title, set_words_info
from app.infrastructure.cache_system import get_cache_manager
from app.media import MediaCache
from app.schemas.words import WordDTO, WordGroupExportDTO
from app.di import container


class WordsService:
    """
    自定义识别词业务服务
    负责：
    - 词组/词汇的增删改查业务编排
    - 导入导出编解码
    - 与 TMDB 媒体信息的联动查询
    - 集数偏移格式校验
    - 标题处理（屏蔽、替换、集偏移）
    """

    words_info: list = []
    _cache_time: float = 0
    _cache_ttl: float = 60

    def __init__(self, media_cache: MediaCache | None = None):
        self._media_cache = media_cache or container.media_cache()
        self._cache = get_cache_manager().get_or_create("words_process", cache_type="memory", maxsize=1000)
        self._refresh()

    def _refresh(self):
        self.word_repo = container.custom_word_repo()
        self.group_repo = container.custom_word_group_repo()
        self._load_words_with_cache()

    def _load_words_with_cache(self):
        current_time = time.time()
        if current_time - self._cache_time > self._cache_ttl or not self.words_info:
            self.words_info = self.word_repo.get_custom_words(enabled=1)
            set_words_info(self.words_info)
            self._cache_time = current_time
            self._cache.clear()

    def clear_cache(self):
        self._cache_time = 0
        self._cache.clear()
        self._refresh()

    # ---------- 标题处理 ----------

    def process(self, title):
        cached_result = self._cache.get(title)
        if cached_result is not None:
            return cached_result
        self._load_words_with_cache()
        result = process_title(self.words_info, title)
        self._cache.set(title, result)
        return result

    # ---------- 词组操作 ----------

    def add_word_group(self, tmdb_id: int, tmdb_type: str) -> None:
        if tmdb_type == "tv":
            if self.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=2):
                raise ResourceAlreadyExistsError("识别词组（TMDB ID）已存在")
            tmdb_info = self._media_cache.get_tmdb_info(mtype=MediaType.TV, tmdbid=tmdb_id)
            if not tmdb_info:
                raise ResourceNotFoundError("添加失败，无法查询到TMDB信息")
            self.insert_custom_word_groups(
                title=tmdb_info.get("name"),
                year=tmdb_info.get("first_air_date", "")[0:4],
                gtype=2,
                tmdbid=tmdb_id,
                season_count=tmdb_info.get("number_of_seasons"),
            )
        elif tmdb_type == "movie":
            if self.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=1):
                raise ResourceAlreadyExistsError("识别词组（TMDB ID）已存在")
            tmdb_info = self._media_cache.get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tmdb_id)
            if not tmdb_info:
                raise ResourceNotFoundError("添加失败，无法查询到TMDB信息")
            self.insert_custom_word_groups(
                title=tmdb_info.get("title"),
                year=tmdb_info.get("release_date", "")[0:4],
                gtype=1,
                tmdbid=tmdb_id,
                season_count=0,
            )
        else:
            raise ValidationError("无法识别媒体类型")

    def delete_word_group(self, gid: int) -> None:
        self.group_repo.delete_custom_word_group(gid=gid)
        self._refresh()

    # ---------- 词汇操作 ----------

    @staticmethod
    def _validate_offset(wtype: str, offset: str) -> str | None:
        temp = CustomWordEntity(
            id=0,
            replaced=None,
            replace=None,
            front="",
            back="",
            offset=offset or "",
            type=int(wtype) if wtype in ("3", "4") else 1,
            group_id=0,
            season=0,
            enabled=1,
            regex=0,
            help=None,
            note=None,
        )
        return temp.validate_offset()

    def add_or_edit_word(
        self,
        wid,
        gid,
        group_type,
        replaced,
        replace,
        front,
        back,
        offset,
        whelp,
        wtype,
        season,
        enabled,
        regex,
    ) -> None:
        err = self._validate_offset(wtype, offset)
        if err:
            raise ValidationError(err)
        if wid:
            self.delete_custom_word(wid=wid)
        if group_type == "1":
            season = -2
        wtype_int = int(wtype)
        if wtype_int == 1:
            if self.is_custom_words_existed(replaced=replaced):
                raise ResourceAlreadyExistsError(f"识别词已存在（被替换词：{replaced}）")
            self.insert_custom_word(
                replaced=replaced,
                replace="",
                front="",
                back="",
                offset="",
                wtype=wtype_int,
                gid=gid,
                season=season,
                enabled=enabled,
                regex=regex,
                whelp=whelp or "",
            )
        elif wtype_int == 2:
            if self.is_custom_words_existed(replaced=replaced):
                raise ResourceAlreadyExistsError(f"识别词已存在（被替换词：{replaced}）")
            self.insert_custom_word(
                replaced=replaced,
                replace=replace,
                front="",
                back="",
                offset="",
                wtype=wtype_int,
                gid=gid,
                season=season,
                enabled=enabled,
                regex=regex,
                whelp=whelp or "",
            )
        elif wtype_int == 4:
            if self.is_custom_words_existed(front=front, back=back):
                raise ResourceAlreadyExistsError(f"识别词已存在（前后定位词：{front}@{back}）")
            self.insert_custom_word(
                replaced="",
                replace="",
                front=front,
                back=back,
                offset=offset,
                wtype=wtype_int,
                gid=gid,
                season=season,
                enabled=enabled,
                regex=regex,
                whelp=whelp or "",
            )
        elif wtype_int == 3:
            if self.is_custom_words_existed(replaced=replaced):
                raise ResourceAlreadyExistsError(f"识别词已存在（被替换词：{replaced}）")
            self.insert_custom_word(
                replaced=replaced,
                replace=replace,
                front=front,
                back=back,
                offset=offset,
                wtype=wtype_int,
                gid=gid,
                season=season,
                enabled=enabled,
                regex=regex,
                whelp=whelp or "",
            )

    def delete_word(self, wid: int | None = None) -> None:
        self.delete_custom_word(wid=wid)

    def delete_words_by_ids(self, ids_info: list[str]) -> None:
        if not ids_info:
            self.delete_custom_word()
            return
        for id_info in ids_info:
            wid = id_info.split("_")[1] if "_" in str(id_info) else id_info
            self.delete_custom_word(wid=wid)

    def toggle_words(self, ids_info: list[str], flag: str) -> None:
        flag_map = {"enable": 1, "disable": 0}
        enabled = flag_map.get(flag)
        if enabled is None:
            raise ValidationError(f"无效的状态标志: {flag}")
        if not ids_info:
            self.check_custom_word(enabled=enabled)
        else:
            for id_info in ids_info:
                wid = id_info.split("_")[1] if "_" in str(id_info) else id_info
                self.check_custom_word(wid=wid, enabled=enabled)

    def get_word_by_id(self, wid: int) -> WordDTO | None:
        rows = self.get_custom_words(wid=wid)
        if not rows:
            return None
        r = rows[0]
        return WordDTO(
            id=r.ID,
            replaced=r.REPLACED,
            replace=r.REPLACE,
            front=r.FRONT,
            back=r.BACK,
            offset=r.OFFSET,
            type=r.TYPE,
            group_id=r.GROUP_ID,
            season=r.SEASON,
            enabled=r.ENABLED,
            regex=r.REGEX,
            help=r.HELP,
        )

    # ---------- 导入导出 ----------

    def analyse_import_code(self, import_code: str) -> tuple[list[WordGroupExportDTO], str]:
        raw = base64.b64decode(import_code.encode("utf-8")).decode("utf-8")
        parts = raw.split("@@@@@@")
        import_dict = json.loads(parts[0])
        note = parts[1] if len(parts) > 1 else ""
        groups = []
        for group in import_dict.values():
            tmdbid = group.get("tmdbid")
            wtype = group.get("type")
            link = ""
            if tmdbid:
                link = "https://www.themoviedb.org/{}/{}".format("movie" if int(wtype) == 1 else "tv", tmdbid)
            groups.append(
                WordGroupExportDTO(
                    id=str(group.get("id", "")),
                    name="{}（{}）".format(group.get("title"), group.get("year"))
                    if group.get("year")
                    else group.get("title", ""),
                    link=link,
                    type=wtype,
                    seasons=group.get("season_count") or "",
                    words=group.get("words", {}),
                )
            )
        return groups, note

    def export_words(self, ids_info: str | None = None, note: str = "") -> tuple[str, str]:
        group_ids = []
        word_ids = []
        group_infos = []
        word_infos = []
        if ids_info:
            id_pairs = ids_info.split("@")
            for id_pair in id_pairs:
                parts = id_pair.split("_")
                if len(parts) >= 2:
                    group_ids.append(parts[0])
                    word_ids.append(parts[1])
            for gid in group_ids:
                if gid != "-1":
                    info = self.get_custom_word_groups(gid=gid)
                    if info:
                        group_infos.append(info[0])
            for wid in word_ids:
                info = self.get_custom_words(wid=wid)
                if info:
                    word_infos.append(info[0])
        else:
            group_infos = self.get_custom_word_groups()
            word_infos = self.get_custom_words()
        export_dict = {}
        if not group_ids or "-1" in group_ids:
            export_dict["-1"] = {"id": -1, "title": "通用", "type": 1, "words": {}}
        for g in group_infos:
            export_dict[str(g.ID)] = {
                "id": g.ID,
                "title": g.TITLE,
                "year": g.YEAR,
                "type": g.TYPE,
                "tmdbid": g.TMDBID,
                "season_count": g.SEASON_COUNT,
                "words": {},
            }
        for w in word_infos:
            export_dict.get(str(w.GROUP_ID), {}).setdefault("words", {})[str(w.ID)] = {
                "id": w.ID,
                "replaced": w.REPLACED,
                "replace": w.REPLACE,
                "front": w.FRONT,
                "back": w.BACK,
                "offset": w.OFFSET,
                "type": w.TYPE,
                "season": w.SEASON,
                "regex": w.REGEX,
                "help": w.HELP,
            }
        export_string = json.dumps(export_dict) + "@@@@@@" + str(note)
        encoded = base64.b64encode(export_string.encode("utf-8")).decode("utf-8")
        return encoded, note

    def import_words(self, import_code: str, ids_info: str) -> None:
        raw = base64.b64decode(import_code.encode("utf-8")).decode("utf-8")
        parts = raw.split("@@@@@@")
        import_dict = json.loads(parts[0])
        import_group_ids = [id_info.split("_")[0] for id_info in ids_info.split("@") if "_" in id_info]
        group_id_map = {}
        for import_group_id in import_group_ids:
            group_info = import_dict.get(import_group_id)
            if not group_info:
                continue
            if int(group_info.get("id", 0)) == -1:
                group_id_map["-1"] = -1
                continue
            title = group_info.get("title")
            year = group_info.get("year")
            gtype = group_info.get("type")
            tmdbid = group_info.get("tmdbid")
            season_count = group_info.get("season_count")
            if not self.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype):
                self.insert_custom_word_groups(
                    title=title,
                    year=year,
                    gtype=gtype,
                    tmdbid=tmdbid,
                    season_count=season_count,
                )
            existing = self.get_custom_word_groups(tmdbid=tmdbid, gtype=gtype)
            if existing:
                group_id_map[import_group_id] = existing[0].ID
        for id_info in ids_info.split("@"):
            if "_" not in id_info:
                continue
            igid, iwid = id_info.split("_")[0], id_info.split("_")[1]
            word_data = import_dict.get(igid, {}).get("words", {}).get(iwid)
            if not word_data:
                continue
            gid = group_id_map.get(igid)
            replaced = word_data.get("replaced")
            replace = word_data.get("replace")
            front = word_data.get("front")
            back = word_data.get("back")
            offset = word_data.get("offset")
            whelp = word_data.get("help")
            wtype = int(word_data.get("type", 1))
            season = word_data.get("season")
            regex = word_data.get("regex")
            if wtype in (1, 2, 3):
                if self.is_custom_words_existed(replaced=replaced):
                    raise ResourceAlreadyExistsError(f"识别词已存在（被替换词：{replaced}）")
            elif wtype == 4:
                if self.is_custom_words_existed(front=front, back=back):
                    raise ResourceAlreadyExistsError(f"识别词已存在（前后定位词：{front}@{back}）")
            self.insert_custom_word(
                replaced=replaced or "",
                replace=replace or "",
                front=front or "",
                back=back or "",
                offset=offset or "",
                wtype=wtype,
                gid=gid,
                season=season,
                enabled=1,
                regex=regex,
                whelp=whelp or "",
            )

    # ---------- 列表查询 ----------

    def get_all_word_groups(self) -> list[dict]:
        groups = []
        words_info = self.get_custom_words(gid=-1)
        words = []
        for w in words_info:
            words.append(
                {
                    "id": w.ID,
                    "replaced": w.REPLACED,
                    "replace": w.REPLACE,
                    "front": w.FRONT,
                    "back": w.BACK,
                    "offset": w.OFFSET,
                    "type": w.TYPE,
                    "group_id": w.GROUP_ID,
                    "season": w.SEASON,
                    "enabled": w.ENABLED,
                    "regex": w.REGEX,
                    "help": w.HELP,
                }
            )
        groups.append({"id": "-1", "name": "通用", "link": "", "type": "1", "seasons": "0", "words": words})
        group_infos = self.get_custom_word_groups()
        for g in group_infos:
            gid = g.ID
            name = f"{g.TITLE} ({g.YEAR})"
            gtype = g.TYPE
            link = (
                f"https://www.themoviedb.org/movie/{g.TMDBID}"
                if gtype == 1
                else f"https://www.themoviedb.org/tv/{g.TMDBID}"
            )
            words = []
            words_info = self.get_custom_words(gid=gid)
            for w in words_info:
                words.append(
                    {
                        "id": w.ID,
                        "replaced": w.REPLACED,
                        "replace": w.REPLACE,
                        "front": w.FRONT,
                        "back": w.BACK,
                        "offset": w.OFFSET,
                        "type": w.TYPE,
                        "group_id": w.GROUP_ID,
                        "season": w.SEASON,
                        "enabled": w.ENABLED,
                        "regex": w.REGEX,
                        "help": w.HELP,
                    }
                )
            groups.append(
                {
                    "id": gid,
                    "name": name,
                    "link": link,
                    "type": g.TYPE,
                    "seasons": g.SEASON_COUNT,
                    "words": words,
                }
            )
        return groups

    # ---------- 原 WordsHelper CRUD ----------

    def is_custom_words_existed(self, replaced=None, front=None, back=None):
        return self.word_repo.is_custom_words_existed(replaced=replaced, front=front, back=back)

    def insert_custom_word(
        self, replaced, replace, front, back, offset, wtype, gid, season, enabled, regex, whelp, note=None
    ):
        ret = self.word_repo.insert_custom_word(
            replaced=replaced,
            replace=replace,
            front=front,
            back=back,
            offset=offset,
            wtype=wtype,
            gid=gid,
            season=season,
            enabled=enabled,
            regex=regex,
            whelp=whelp,
            note=note,
        )
        self._refresh()
        return ret

    def delete_custom_word(self, wid=None):
        ret = self.word_repo.delete_custom_word(wid=wid)
        self._refresh()
        return ret

    def get_custom_words(self, wid=None, gid=None, enabled=None):
        return self.word_repo.get_custom_words(wid=wid, gid=gid, enabled=enabled)

    def get_custom_word_groups(self, gid=None, tmdbid=None, gtype=None):
        return self.group_repo.get_custom_word_groups(gid=gid, tmdbid=tmdbid, gtype=gtype)

    def is_custom_word_group_existed(self, tmdbid=None, gtype=None):
        return self.group_repo.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype)

    def insert_custom_word_groups(self, title, year, gtype, tmdbid, season_count, note=None):
        ret = self.group_repo.insert_custom_word_groups(
            title=title,
            year=year,
            gtype=gtype,
            tmdbid=tmdbid,
            season_count=season_count,
            note=note,
        )
        self._refresh()
        return ret

    def check_custom_word(self, wid=None, enabled=None):
        ret = self.word_repo.check_custom_word(wid=wid, enabled=enabled)
        self._refresh()
        return ret
