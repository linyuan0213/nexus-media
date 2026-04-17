from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
import base64
import json
import re
from app.helper import WordsHelper
from app.media import Category, Media
from app.utils import ExceptionUtils
from app.utils.types import MediaType

words_bp = Blueprint("words", __name__, url_prefix="/api/web/words")

@words_bp.route('/add_custom_word_group', methods=['POST'])
@any_auth
@parse_json_data
def _add_custom_word_group(data):
        try:
            tmdb_id = data.get("tmdb_id")
            tmdb_type = data.get("tmdb_type")
            _wordshelper = WordsHelper()
            _media = Media()
            if tmdb_type == "tv":
                if not _wordshelper.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=2):
                    tmdb_info = _media.get_tmdb_info(
                        mtype=MediaType.TV, tmdbid=tmdb_id)
                    if not tmdb_info:
                        return fail(msg="添加失败，无法查询到TMDB信息")
                    _wordshelper.insert_custom_word_groups(title=tmdb_info.get("name"),
                                                           year=tmdb_info.get(
                                                               "first_air_date")[0:4],
                                                           gtype=2,
                                                           tmdbid=tmdb_id,
                                                           season_count=tmdb_info.get("number_of_seasons"))
                    return success(msg="")
                else:
                    return fail(msg="识别词组（TMDB ID）已存在")
            elif tmdb_type == "movie":
                if not _wordshelper.is_custom_word_group_existed(tmdbid=tmdb_id, gtype=1):
                    tmdb_info = _media.get_tmdb_info(
                        mtype=MediaType.MOVIE, tmdbid=tmdb_id)
                    if not tmdb_info:
                        return fail(msg="添加失败，无法查询到TMDB信息")
                    _wordshelper.insert_custom_word_groups(title=tmdb_info.get("title"),
                                                           year=tmdb_info.get(
                                                               "release_date")[0:4],
                                                           gtype=1,
                                                           tmdbid=tmdb_id,
                                                           season_count=0)
                    return success(msg="")
                else:
                    return fail(msg="识别词组（TMDB ID）已存在")
            else:
                return fail(msg="无法识别媒体类型")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/add_or_edit_custom_word', methods=['POST'])
@any_auth
@parse_json_data
def _add_or_edit_custom_word(data):
        try:
            wid = data.get("id")
            gid = data.get("gid")
            group_type = data.get("group_type")
            replaced = data.get("new_replaced")
            replace = data.get("new_replace")
            front = data.get("new_front")
            back = data.get("new_back")
            offset = data.get("new_offset")
            whelp = data.get("new_help")
            wtype = data.get("type")
            season = data.get("season")
            enabled = data.get("enabled")
            regex = data.get("regex")

            _wordshelper = WordsHelper()

            # 集数偏移格式检查
            if wtype in ["3", "4"]:
                if not re.findall(r'EP', offset):
                    return fail(msg="偏移集数格式有误")
                if re.findall(r'(?!-|\+|\*|/|[0-9]).', re.sub(r'EP', "", offset)):
                    return fail(msg="偏移集数格式有误")
            if wid:
                _wordshelper.delete_custom_word(wid=wid)
            # 电影
            if group_type == "1":
                season = -2
            # 屏蔽
            if wtype == "1":
                if not _wordshelper.is_custom_words_existed(replaced=replaced):
                    _wordshelper.insert_custom_word(replaced=replaced,
                                                    replace="",
                                                    front="",
                                                    back="",
                                                    offset="",
                                                    wtype=wtype,
                                                    gid=gid,
                                                    season=season,
                                                    enabled=enabled,
                                                    regex=regex,
                                                    whelp=whelp if whelp else "")
                    return success(msg="")
                else:
                    return fail(msg="识别词已存在\n（被替换词：%s）" % replaced)
            # 替换
            elif wtype == "2":
                if not _wordshelper.is_custom_words_existed(replaced=replaced):
                    _wordshelper.insert_custom_word(replaced=replaced,
                                                    replace=replace,
                                                    front="",
                                                    back="",
                                                    offset="",
                                                    wtype=wtype,
                                                    gid=gid,
                                                    season=season,
                                                    enabled=enabled,
                                                    regex=regex,
                                                    whelp=whelp if whelp else "")
                    return success(msg="")
                else:
                    return fail(msg="识别词已存在\n（被替换词：%s）" % replaced)
            # 集偏移
            elif wtype == "4":
                if not _wordshelper.is_custom_words_existed(front=front, back=back):
                    _wordshelper.insert_custom_word(replaced="",
                                                    replace="",
                                                    front=front,
                                                    back=back,
                                                    offset=offset,
                                                    wtype=wtype,
                                                    gid=gid,
                                                    season=season,
                                                    enabled=enabled,
                                                    regex=regex,
                                                    whelp=whelp if whelp else "")
                    return success(msg="")
                else:
                    return fail(msg="识别词已存在\n（前后定位词：%s@%s）" % (front, back))
            # 替换+集偏移
            elif wtype == "3":
                if not _wordshelper.is_custom_words_existed(replaced=replaced):
                    _wordshelper.insert_custom_word(replaced=replaced,
                                                    replace=replace,
                                                    front=front,
                                                    back=back,
                                                    offset=offset,
                                                    wtype=wtype,
                                                    gid=gid,
                                                    season=season,
                                                    enabled=enabled,
                                                    regex=regex,
                                                    whelp=whelp if whelp else "")
                    return success(msg="")
                else:
                    return fail(msg="识别词已存在\n（被替换词：%s）" % replaced)
            else:
                return fail(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/analyse_import_custom_words_code', methods=['POST'])
@any_auth
@parse_json_data
def _analyse_import_custom_words_code(data):
        try:
            import_code = data.get('import_code')
            string = base64.b64decode(import_code.encode(
                "utf-8")).decode('utf-8').split("@@@@@@")
            note_string = string[1]
            import_dict = json.loads(string[0])
            groups = []
            for group in import_dict.values():
                wid = group.get('id')
                title = group.get("title")
                year = group.get("year")
                wtype = group.get("type")
                tmdbid = group.get("tmdbid")
                season_count = group.get("season_count") or ""
                words = group.get("words")
                if tmdbid:
                    link = "https://www.themoviedb.org/%s/%s" % (
                        "movie" if int(wtype) == 1 else "tv", tmdbid)
                else:
                    link = ""
                groups.append({"id": wid,
                               "name": "%s（%s）" % (title, year) if year else title,
                               "link": link,
                               "type": wtype,
                               "seasons": season_count,
                               "words": words})
            return success(groups=groups, note_string=note_string)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/check_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _check_custom_words(data):
        try:
            flag_dict = {"enable": 1, "disable": 0}
            ids_info = data.get("ids_info")
            enabled = flag_dict.get(data.get("flag"))
            _wordshelper = WordsHelper()
            if not ids_info:
                _wordshelper.check_custom_word(enabled=enabled)
            else:
                ids = [id_info.split("_")[1] for id_info in ids_info]
                for wid in ids:
                    _wordshelper.check_custom_word(wid=wid, enabled=enabled)
            return success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg="识别词状态设置失败")

@words_bp.route('/delete_custom_word_group', methods=['POST'])
@any_auth
@parse_json_data
def _delete_custom_word_group(data):
        try:
            gid = data.get("gid")
            WordsHelper().delete_custom_word_group(gid=gid)
            return success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/delete_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _delete_custom_words(data):
        try:
            _wordshelper = WordsHelper()
            ids_info = data.get("ids_info")
            if not ids_info:
                _wordshelper.delete_custom_word()
            else:
                ids = [id_info.split("_")[1] for id_info in ids_info]
                for wid in ids:
                    _wordshelper.delete_custom_word(wid=wid)
            return success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/export_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _export_custom_words(data):
        try:
            note = data.get("note")
            ids_info = data.get("ids_info")
            group_ids = []
            word_ids = []
            group_infos = []
            word_infos = []

            _wordshelper = WordsHelper()

            if ids_info:
                ids_info = ids_info.split("@")
                for id_info in ids_info:
                    wid = id_info.split("_")
                    group_ids.append(wid[0])
                    word_ids.append(wid[1])
                for group_id in group_ids:
                    if group_id != "-1":
                        group_info = _wordshelper.get_custom_word_groups(
                            gid=group_id)
                        if group_info:
                            group_infos.append(group_info[0])
                for word_id in word_ids:
                    word_info = _wordshelper.get_custom_words(wid=word_id)
                    if word_info:
                        word_infos.append(word_info[0])
            else:
                group_infos = _wordshelper.get_custom_word_groups()
                word_infos = _wordshelper.get_custom_words()
            export_dict = {}
            if not group_ids or "-1" in group_ids:
                export_dict["-1"] = {"id": -1,
                                     "title": "通用",
                                     "type": 1,
                                     "words": {}, }
            for group_info in group_infos:
                export_dict[str(group_info.ID)] = {"id": group_info.ID,
                                                   "title": group_info.TITLE,
                                                   "year": group_info.YEAR,
                                                   "type": group_info.TYPE,
                                                   "tmdbid": group_info.TMDBID,
                                                   "season_count": group_info.SEASON_COUNT,
                                                   "words": {}, }
            for word_info in word_infos:
                export_dict[str(word_info.GROUP_ID)]["words"][str(word_info.ID)] = {"id": word_info.ID,
                                                                                    "replaced": word_info.REPLACED,
                                                                                    "replace": word_info.REPLACE,
                                                                                    "front": word_info.FRONT,
                                                                                    "back": word_info.BACK,
                                                                                    "offset": word_info.OFFSET,
                                                                                    "type": word_info.TYPE,
                                                                                    "season": word_info.SEASON,
                                                                                    "regex": word_info.REGEX,
                                                                                    "help": word_info.HELP, }
            export_string = json.dumps(export_dict) + "@@@@@@" + str(note)
            string = base64.b64encode(
                export_string.encode("utf-8")).decode('utf-8')
            return success(string=string)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/get_custom_word', methods=['POST'])
@any_auth
@parse_json_data
def _get_custom_word(data):
        try:
            wid = data.get("wid")
            word_info = WordsHelper().get_custom_words(wid=wid)
            if word_info:
                word_info = word_info[0]
                word = {"id": word_info.ID,
                        "replaced": word_info.REPLACED,
                        "replace": word_info.REPLACE,
                        "front": word_info.FRONT,
                        "back": word_info.BACK,
                        "offset": word_info.OFFSET,
                        "type": word_info.TYPE,
                        "group_id": word_info.GROUP_ID,
                        "season": word_info.SEASON,
                        "enabled": word_info.ENABLED,
                        "regex": word_info.REGEX,
                        "help": word_info.HELP, }
            else:
                word = {}
            return success(data=word)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg="查询识别词失败")

@words_bp.route('/import_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _import_custom_words(data):
        try:
            _wordshelper = WordsHelper()
            import_code = data.get('import_code')
            ids_info = data.get('ids_info')
            string = base64.b64decode(import_code.encode(
                "utf-8")).decode('utf-8').split("@@@@@@")
            import_dict = json.loads(string[0])
            import_group_ids = [id_info.split("_")[0] for id_info in ids_info]
            group_id_dict = {}
            for import_group_id in import_group_ids:
                import_group_info = import_dict.get(import_group_id)
                if int(import_group_info.get("id")) == -1:
                    group_id_dict["-1"] = -1
                    continue
                title = import_group_info.get("title")
                year = import_group_info.get("year")
                gtype = import_group_info.get("type")
                tmdbid = import_group_info.get("tmdbid")
                season_count = import_group_info.get("season_count")
                if not _wordshelper.is_custom_word_group_existed(tmdbid=tmdbid, gtype=gtype):
                    _wordshelper.insert_custom_word_groups(title=title,
                                                           year=year,
                                                           gtype=gtype,
                                                           tmdbid=tmdbid,
                                                           season_count=season_count)
                group_info = _wordshelper.get_custom_word_groups(
                    tmdbid=tmdbid, gtype=gtype)
                if group_info:
                    group_id_dict[import_group_id] = group_info[0].ID
            for id_info in ids_info:
                id_info = id_info.split('_')
                import_group_id = id_info[0]
                import_word_id = id_info[1]
                import_word_info = import_dict.get(
                    import_group_id).get("words").get(import_word_id)
                gid = group_id_dict.get(import_group_id)
                replaced = import_word_info.get("replaced")
                replace = import_word_info.get("replace")
                front = import_word_info.get("front")
                back = import_word_info.get("back")
                offset = import_word_info.get("offset")
                whelp = import_word_info.get("help")
                wtype = int(import_word_info.get("type"))
                season = import_word_info.get("season")
                regex = import_word_info.get("regex")
                # 屏蔽, 替换, 替换+集偏移
                if wtype in [1, 2, 3]:
                    if _wordshelper.is_custom_words_existed(replaced=replaced):
                        return fail(msg="识别词已存在\n（被替换词：%s）" % replaced)
                # 集偏移
                elif wtype == 4:
                    if _wordshelper.is_custom_words_existed(front=front, back=back):
                        return fail(msg="识别词已存在\n（前后定位词：%s@%s）" % (front, back))
                _wordshelper.insert_custom_word(replaced=replaced,
                                                replace=replace,
                                                front=front,
                                                back=back,
                                                offset=offset,
                                                wtype=wtype,
                                                gid=gid,
                                                season=season,
                                                enabled=1,
                                                regex=regex,
                                                whelp=whelp if whelp else "")
            return success(msg="")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return fail(msg=str(e))

@words_bp.route('/get_categories', methods=['POST'])
@any_auth
@parse_json_data
def get_categories(data):
        if data.get("type") == "电影":
            categories = Category().movie_categorys
        elif data.get("type") == "电视剧":
            categories = Category().tv_categorys
        else:
            categories = Category().anime_categorys
        return success(category=list(categories), id=data.get("id"), value=data.get("value"))

@words_bp.route('/get_customwords', methods=['POST'])
@any_auth
@parse_json_data
def get_customwords(data):
        _wordshelper = WordsHelper()
        words = []
        words_info = _wordshelper.get_custom_words(gid=-1)
        for word_info in words_info:
            words.append({"id": word_info.ID,
                          "replaced": word_info.REPLACED,
                          "replace": word_info.REPLACE,
                          "front": word_info.FRONT,
                          "back": word_info.BACK,
                          "offset": word_info.OFFSET,
                          "type": word_info.TYPE,
                          "group_id": word_info.GROUP_ID,
                          "season": word_info.SEASON,
                          "enabled": word_info.ENABLED,
                          "regex": word_info.REGEX,
                          "help": word_info.HELP, })
        groups = [{"id": "-1",
                   "name": "通用",
                   "link": "",
                   "type": "1",
                   "seasons": "0",
                   "words": words}]
        groups_info = _wordshelper.get_custom_word_groups()
        for group_info in groups_info:
            gid = group_info.ID
            name = "%s (%s)" % (group_info.TITLE, group_info.YEAR)
            gtype = group_info.TYPE
            if gtype == 1:
                link = "https://www.themoviedb.org/movie/%s" % group_info.TMDBID
            else:
                link = "https://www.themoviedb.org/tv/%s" % group_info.TMDBID
            words = []
            words_info = _wordshelper.get_custom_words(gid=gid)
            for word_info in words_info:
                words.append({"id": word_info.ID,
                              "replaced": word_info.REPLACED,
                              "replace": word_info.REPLACE,
                              "front": word_info.FRONT,
                              "back": word_info.BACK,
                              "offset": word_info.OFFSET,
                              "type": word_info.TYPE,
                              "group_id": word_info.GROUP_ID,
                              "season": word_info.SEASON,
                              "enabled": word_info.ENABLED,
                              "regex": word_info.REGEX,
                              "help": word_info.HELP, })
            groups.append({"id": gid,
                           "name": name,
                           "link": link,
                           "type": group_info.TYPE,
                           "seasons": group_info.SEASON_COUNT,
                           "words": words})
        return success(result=groups)

