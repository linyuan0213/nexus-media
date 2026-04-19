from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.media import Category
from app.services.words_service import WordsService
from app.utils import ExceptionUtils

words_bp = Blueprint("words", __name__, url_prefix="/api/web/words")


@words_bp.route('/add_custom_word_group', methods=['POST'])
@any_auth
@parse_json_data
def _add_custom_word_group(data):
    try:
        svc = WordsService()
        ok, msg = svc.add_word_group(
            tmdb_id=data.get("tmdb_id"),
            tmdb_type=data.get("tmdb_type")
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/add_or_edit_custom_word', methods=['POST'])
@any_auth
@parse_json_data
def _add_or_edit_custom_word(data):
    try:
        svc = WordsService()
        ok, msg = svc.add_or_edit_word(
            wid=data.get("id"),
            gid=data.get("gid"),
            group_type=data.get("group_type"),
            replaced=data.get("new_replaced"),
            replace=data.get("new_replace"),
            front=data.get("new_front"),
            back=data.get("new_back"),
            offset=data.get("new_offset"),
            whelp=data.get("new_help"),
            wtype=data.get("type"),
            season=data.get("season"),
            enabled=data.get("enabled"),
            regex=data.get("regex")
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/analyse_import_custom_words_code', methods=['POST'])
@any_auth
@parse_json_data
def _analyse_import_custom_words_code(data):
    try:
        svc = WordsService()
        groups, note = svc.analyse_import_code(data.get('import_code'))
        return success(groups=[{
            "id": g.id,
            "name": g.name,
            "link": g.link,
            "type": g.type,
            "seasons": g.seasons,
            "words": g.words
        } for g in groups], note_string=note)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/check_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _check_custom_words(data):
    try:
        svc = WordsService()
        ok = svc.toggle_words(
            ids_info=data.get("ids_info") or [],
            flag=data.get("flag")
        )
        if ok:
            return success(msg="")
        return fail(msg="识别词状态设置失败")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="识别词状态设置失败")


@words_bp.route('/delete_custom_word_group', methods=['POST'])
@any_auth
@parse_json_data
def _delete_custom_word_group(data):
    try:
        WordsService().delete_word_group(data.get("gid"))
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/delete_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _delete_custom_words(data):
    try:
        ids = data.get("ids_info")
        WordsService().delete_words_by_ids(ids if ids else [])
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/export_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _export_custom_words(data):
    try:
        svc = WordsService()
        encoded, _ = svc.export_words(
            ids_info=data.get("ids_info"),
            note=data.get("note")
        )
        return success(string=encoded)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@words_bp.route('/get_custom_word', methods=['POST'])
@any_auth
@parse_json_data
def _get_custom_word(data):
    try:
        word = WordsService().get_word_by_id(data.get("wid"))
        if word:
            return success(data={
                "id": word.id,
                "replaced": word.replaced,
                "replace": word.replace,
                "front": word.front,
                "back": word.back,
                "offset": word.offset,
                "type": word.type,
                "group_id": word.group_id,
                "season": word.season,
                "enabled": word.enabled,
                "regex": word.regex,
                "help": word.help,
            })
        return success(data={})
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="查询识别词失败")


@words_bp.route('/import_custom_words', methods=['POST'])
@any_auth
@parse_json_data
def _import_custom_words(data):
    try:
        svc = WordsService()
        ok, msg = svc.import_words(
            import_code=data.get('import_code'),
            ids_info=data.get('ids_info')
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
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
    try:
        groups = WordsService().get_all_word_groups()
        return success(result=groups)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))
