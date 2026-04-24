# -*- coding: utf-8 -*-
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user, get_words_service
from app.media import Category
from app.services.words_service import WordsService
from app.utils import ExceptionUtils
from app.utils.response import success, fail

router = APIRouter()


# ---------- Request Models ----------

class AddCustomWordGroupRequest(BaseModel):
    tmdb_id: int
    tmdb_type: str


class AddOrEditCustomWordRequest(BaseModel):
    id: Optional[int] = None
    gid: int
    group_type: str
    new_replaced: str
    new_replace: str
    new_front: str
    new_back: str
    new_offset: str
    new_help: str
    type: str
    season: Optional[int] = None
    enabled: int
    regex: int


class AnalyseImportCodeRequest(BaseModel):
    import_code: str


class CheckCustomWordsRequest(BaseModel):
    ids_info: Optional[List[str]] = None
    flag: Optional[str] = None


class DeleteCustomWordGroupRequest(BaseModel):
    gid: int


class DeleteCustomWordsRequest(BaseModel):
    ids_info: Optional[List[str]] = None


class ExportCustomWordsRequest(BaseModel):
    ids_info: Optional[str] = None
    note: Optional[str] = None


class GetCustomWordRequest(BaseModel):
    wid: int


class ImportCustomWordsRequest(BaseModel):
    import_code: str
    ids_info: str


class GetCategoriesRequest(BaseModel):
    type: str
    id: Optional[str] = None
    value: Optional[str] = None


# ---------- Endpoints ----------

@router.post("/add_custom_word_group")
def add_custom_word_group(
    req: AddCustomWordGroupRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        ok, msg = svc.add_word_group(
            tmdb_id=req.tmdb_id,
            tmdb_type=req.tmdb_type,
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/add_or_edit_custom_word")
def add_or_edit_custom_word(
    req: AddOrEditCustomWordRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        ok, msg = svc.add_or_edit_word(
            wid=req.id or 0,
            gid=req.gid,
            group_type=req.group_type,
            replaced=req.new_replaced,
            replace=req.new_replace,
            front=req.new_front,
            back=req.new_back,
            offset=req.new_offset,
            whelp=req.new_help,
            wtype=req.type,
            season=req.season if req.season is not None else -2,
            enabled=req.enabled,
            regex=req.regex,
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/analyse_import_custom_words_code")
def analyse_import_custom_words_code(
    req: AnalyseImportCodeRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        groups, note = svc.analyse_import_code(req.import_code)
        return success(
            groups=[
                {
                    "id": g.id,
                    "name": g.name,
                    "link": g.link,
                    "type": g.type,
                    "seasons": g.seasons,
                    "words": g.words,
                }
                for g in groups
            ],
            note_string=note,
        )
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/check_custom_words")
def check_custom_words(
    req: CheckCustomWordsRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        ok = svc.toggle_words(
            ids_info=req.ids_info or [],
            flag=req.flag or "",
        )
        if ok:
            return success(msg="")
        return fail(msg="识别词状态设置失败")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="识别词状态设置失败")


@router.post("/delete_custom_word_group")
def delete_custom_word_group(
    req: DeleteCustomWordGroupRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        svc.delete_word_group(req.gid)
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/delete_custom_words")
def delete_custom_words(
    req: DeleteCustomWordsRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        svc.delete_words_by_ids(req.ids_info or [])
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/export_custom_words")
def export_custom_words(
    req: ExportCustomWordsRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        encoded, _ = svc.export_words(
            ids_info=req.ids_info,
            note=req.note or "",
        )
        return success(string=encoded)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/get_custom_word")
def get_custom_word(
    req: GetCustomWordRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        word = svc.get_word_by_id(req.wid)
        if word:
            return success(
                data={
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
                }
            )
        return success(data={})
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="查询识别词失败")


@router.post("/import_custom_words")
def import_custom_words(
    req: ImportCustomWordsRequest,
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        ok, msg = svc.import_words(
            import_code=req.import_code,
            ids_info=req.ids_info,
        )
        if ok:
            return success(msg=msg)
        return fail(msg=msg)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))


@router.post("/get_categories")
def get_categories(
    req: GetCategoriesRequest,
    current_user: str = Depends(get_current_user),
):
    if req.type == "电影":
        categories = Category().movie_categorys
    elif req.type == "电视剧":
        categories = Category().tv_categorys
    else:
        categories = Category().anime_categorys
    return success(
        category=list(categories),
        id=req.id,
        value=req.value,
    )


@router.post("/get_customwords")
def get_customwords(
    current_user: str = Depends(get_current_user),
    svc: WordsService = Depends(get_words_service),
):
    try:
        groups = svc.get_all_word_groups()
        return success(result=groups)
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg=str(e))
