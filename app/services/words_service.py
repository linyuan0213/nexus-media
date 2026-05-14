"""
WordsService - 自定义识别词业务层
将 web/controllers/words.py 中的业务逻辑下沉到可独立测试的 Service。
"""
import base64
import json
import re

from app.helper import WordsHelper
from app.media import MediaCache
from app.schemas.words import (
    WordDTO,
    WordGroupExportDTO,
)
from app.utils.types import MediaType


class WordsService:
    """
    自定义识别词业务服务
    负责：
    - 词组/词汇的增删改查业务编排
    - 导入导出编解码
    - 与 TMDB 媒体信息的联动查询
    - 集数偏移格式校验
    """

    def __init__(self, words_helper: WordsHelper | None = None, media_cache: MediaCache | None = None):
        self._words = words_helper or WordsHelper()
        self._media_cache = media_cache or MediaCache()

    # ---------- 词组操作 ----------

    def add_word_group(self, tmdb_id: int, tmdb_type: str) -> tuple[bool, str]:
        """
        根据 TMDB 信息添加自定义词组
        :return: (是否成功, 消息)
        """
        if tmdb_type == "tv":
            if self._words.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=2):
                return False, "识别词组（TMDB ID）已存在"
            tmdb_info = self._media_cache.get_tmdb_info(mtype=MediaType.TV, tmdbid=tmdb_id)
            if not tmdb_info:
                return False, "添加失败，无法查询到TMDB信息"
            self._words.insert_custom_word_groups(
                title=tmdb_info.get("name"),
                year=tmdb_info.get("first_air_date", "")[0:4],
                gtype=2,
                tmdbid=tmdb_id,
                season_count=tmdb_info.get("number_of_seasons")
            )
            return True, ""
        elif tmdb_type == "movie":
            if self._words.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=1):
                return False, "识别词组（TMDB ID）已存在"
            tmdb_info = self._media_cache.get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tmdb_id)
            if not tmdb_info:
                return False, "添加失败，无法查询到TMDB信息"
            self._words.insert_custom_word_groups(
                title=tmdb_info.get("title"),
                year=tmdb_info.get("release_date", "")[0:4],
                gtype=1,
                tmdbid=tmdb_id,
                season_count=0
            )
            return True, ""
        return False, "无法识别媒体类型"

    def delete_word_group(self, gid: int) -> bool:
        """删除自定义词组"""
        self._words.delete_custom_word_group(gid=gid)
        return True

    # ---------- 词汇操作 ----------

    def _validate_offset(self, wtype: str, offset: str) -> str | None:
        """
        校验集数偏移格式
        :return: 错误信息，None 表示通过
        """
        if wtype not in ("3", "4"):
            return None
        if not re.findall(r'EP', offset):
            return "偏移集数格式有误"
        if re.findall(r'(?!-|\+|\*|/|[0-9]).', re.sub(r'EP', "", offset)):
            return "偏移集数格式有误"
        return None

    def add_or_edit_word(self,
                         wid: int,
                         gid: int,
                         group_type: str,
                         replaced: str,
                         replace: str,
                         front: str,
                         back: str,
                         offset: str,
                         whelp: str,
                         wtype: str,
                         season: int,
                         enabled: int,
                         regex: int) -> tuple[bool, str]:
        """
        添加或编辑自定义词
        :return: (是否成功, 消息)
        """
        err = self._validate_offset(wtype, offset)
        if err:
            return False, err

        if wid:
            self._words.delete_custom_word(wid=wid)

        if group_type == "1":
            season = -2

        wtype_int = int(wtype)

        if wtype_int == 1:  # 屏蔽
            if self._words.is_custom_words_existed(replaced=replaced):
                return False, "识别词已存在\n（被替换词：%s）" % replaced
            self._words.insert_custom_word(
                replaced=replaced, replace="", front="", back="", offset="",
                wtype=wtype_int, gid=gid, season=season, enabled=enabled,
                regex=regex, whelp=whelp or ""
            )
            return True, ""

        elif wtype_int == 2:  # 替换
            if self._words.is_custom_words_existed(replaced=replaced):
                return False, "识别词已存在\n（被替换词：%s）" % replaced
            self._words.insert_custom_word(
                replaced=replaced, replace=replace, front="", back="", offset="",
                wtype=wtype_int, gid=gid, season=season, enabled=enabled,
                regex=regex, whelp=whelp or ""
            )
            return True, ""

        elif wtype_int == 4:  # 集偏移
            if self._words.is_custom_words_existed(front=front, back=back):
                return False, "识别词已存在\n（前后定位词：%s@%s）" % (front, back)
            self._words.insert_custom_word(
                replaced="", replace="", front=front, back=back, offset=offset,
                wtype=wtype_int, gid=gid, season=season, enabled=enabled,
                regex=regex, whelp=whelp or ""
            )
            return True, ""

        elif wtype_int == 3:  # 替换+集偏移
            if self._words.is_custom_words_existed(replaced=replaced):
                return False, "识别词已存在\n（被替换词：%s）" % replaced
            self._words.insert_custom_word(
                replaced=replaced, replace=replace, front=front, back=back, offset=offset,
                wtype=wtype_int, gid=gid, season=season, enabled=enabled,
                regex=regex, whelp=whelp or ""
            )
            return True, ""

        return False, ""

    def delete_word(self, wid: int | None = None) -> bool:
        """删除自定义词，wid=None 时删除全部"""
        self._words.delete_custom_word(wid=wid)
        return True

    def delete_words_by_ids(self, ids_info: list[str]) -> bool:
        """根据 id 列表批量删除"""
        if not ids_info:
            self._words.delete_custom_word()
            return True
        for id_info in ids_info:
            wid = id_info.split("_")[1] if "_" in str(id_info) else id_info
            self._words.delete_custom_word(wid=wid)
        return True

    def toggle_words(self, ids_info: list[str], flag: str) -> bool:
        """切换词启用状态"""
        flag_map = {"enable": 1, "disable": 0}
        enabled = flag_map.get(flag)
        if enabled is None:
            return False
        if not ids_info:
            self._words.check_custom_word(enabled=enabled)
        else:
            for id_info in ids_info:
                wid = id_info.split("_")[1] if "_" in str(id_info) else id_info
                self._words.check_custom_word(wid=wid, enabled=enabled)
        return True

    def get_word_by_id(self, wid: int) -> WordDTO | None:
        """根据 ID 获取单个词"""
        rows = self._words.get_custom_words(wid=wid)
        if not rows:
            return None
        r = rows[0]
        return WordDTO(
            id=r.ID, replaced=r.REPLACED, replace=r.REPLACE,
            front=r.FRONT, back=r.BACK, offset=r.OFFSET,
            type=r.TYPE, group_id=r.GROUP_ID, season=r.SEASON,
            enabled=r.ENABLED, regex=r.REGEX, help=r.HELP
        )

    # ---------- 导入导出 ----------

    def analyse_import_code(self, import_code: str) -> tuple[list[WordGroupExportDTO], str]:
        """
        解析导入码
        :return: (词组列表, 备注)
        """
        raw = base64.b64decode(import_code.encode("utf-8")).decode('utf-8')
        parts = raw.split("@@@@@@")
        import_dict = json.loads(parts[0])
        note = parts[1] if len(parts) > 1 else ""
        groups = []
        for group in import_dict.values():
            tmdbid = group.get("tmdbid")
            wtype = group.get("type")
            link = ""
            if tmdbid:
                link = "https://www.themoviedb.org/%s/%s" % (
                    "movie" if int(wtype) == 1 else "tv", tmdbid)
            groups.append(WordGroupExportDTO(
                id=str(group.get('id', '')),
                name="%s（%s）" % (group.get("title"), group.get("year")) if group.get("year") else group.get("title", ""),
                link=link,
                type=wtype,
                seasons=group.get("season_count") or "",
                words=group.get("words", {})
            ))
        return groups, note

    def export_words(self, ids_info: str | None = None, note: str = "") -> tuple[str, str]:
        """
        导出词为 base64 编码字符串
        :return: (编码字符串, 备注)
        """
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
                    info = self._words.get_custom_word_groups(gid=gid)
                    if info:
                        group_infos.append(info[0])
            for wid in word_ids:
                info = self._words.get_custom_words(wid=wid)
                if info:
                    word_infos.append(info[0])
        else:
            group_infos = self._words.get_custom_word_groups()
            word_infos = self._words.get_custom_words()

        export_dict = {}
        if not group_ids or "-1" in group_ids:
            export_dict["-1"] = {
                "id": -1, "title": "通用", "type": 1, "words": {}
            }

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
        encoded = base64.b64encode(export_string.encode("utf-8")).decode('utf-8')
        return encoded, note

    def import_words(self, import_code: str, ids_info: str) -> tuple[bool, str]:
        """
        导入自定义词
        :return: (是否成功, 消息)
        """
        raw = base64.b64decode(import_code.encode("utf-8")).decode('utf-8')
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

            if not self._words.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype):
                self._words.insert_custom_word_groups(
                    title=title, year=year, gtype=gtype,
                    tmdbid=tmdbid, season_count=season_count
                )
            existing = self._words.get_custom_word_groups(tmdbid=tmdbid, gtype=gtype)
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
                if self._words.is_custom_words_existed(replaced=replaced):
                    return False, "识别词已存在\n（被替换词：%s）" % replaced
            elif wtype == 4:
                if self._words.is_custom_words_existed(front=front, back=back):
                    return False, "识别词已存在\n（前后定位词：%s@%s）" % (front, back)

            self._words.insert_custom_word(
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
                whelp=whelp or ""
            )

        return True, ""

    # ---------- 列表查询 ----------

    def get_all_word_groups(self) -> list[dict]:
        """
        获取所有词组（含词汇列表），直接返回前端需要的 dict 结构
        """
        groups = []
        words_info = self._words.get_custom_words(gid=-1)
        words = []
        for w in words_info:
            words.append({
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
            })
        groups.append({
            "id": "-1",
            "name": "通用",
            "link": "",
            "type": "1",
            "seasons": "0",
            "words": words
        })

        group_infos = self._words.get_custom_word_groups()
        for g in group_infos:
            gid = g.ID
            name = "%s (%s)" % (g.TITLE, g.YEAR)
            gtype = g.TYPE
            if gtype == 1:
                link = "https://www.themoviedb.org/movie/%s" % g.TMDBID
            else:
                link = "https://www.themoviedb.org/tv/%s" % g.TMDBID
            words = []
            words_info = self._words.get_custom_words(gid=gid)
            for w in words_info:
                words.append({
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
                })
            groups.append({
                "id": gid,
                "name": name,
                "link": link,
                "type": g.TYPE,
                "seasons": g.SEASON_COUNT,
                "words": words
            })

        return groups
