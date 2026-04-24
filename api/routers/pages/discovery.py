"""
Discovery Pages Router - 发现、搜索、推荐、媒体详情等页面
"""
import json
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import get_current_user, get_searcher_service, get_search_result_service, get_indexer_service
from app.conf import ModuleConf
from app.schemas.auth import UserContext
from app.services.indexer_service import IndexerService
from app.services.search_service import Searcher
from app.services.media_service import SearchResultService

from .utils import templates

router = APIRouter()




@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    s: Optional[str] = Query(None),
    current_user: UserContext = Depends(get_current_user),
    searcher = Depends(get_searcher_service),
    search_result_svc = Depends(get_search_result_service),
    indexer = Depends(get_indexer_service),
):
    """资源搜索页面"""
    pris = ",".join(current_user.permissions) if current_user.permissions else ""
    
    search_results_raw = searcher.get_search_results()
    result = search_result_svc.group_search_results(search_results_raw)
    search_results = result.result
    count = result.total
    
    return templates.TemplateResponse(
        request, "search.html",
        {
            "UserPris": str(pris).split(",") if pris else [],
            "Count": count,
            "Results": search_results,
            "SiteDict": indexer.get_indexer_hash_dict(),
            "UPCHAR": chr(8593),
            "SearchWord": s or ""
        }
    )


@router.get("/recommend", response_class=HTMLResponse)
def recommend_page(
    request: Request,
    type: Optional[str] = Query(""),
    subtype: Optional[str] = Query(""),
    title: Optional[str] = Query(""),
    subtitle: Optional[str] = Query(""),
    page: Optional[str] = Query("1"),
    week: Optional[str] = Query(""),
    tmdbid: Optional[str] = Query(""),
    personid: Optional[str] = Query(""),
    keyword: Optional[str] = Query(""),
    source: Optional[str] = Query(""),
    filter: Optional[str] = Query(""),
    params: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
):
    """推荐页面"""
    params_dict = json.loads(params) if params else {}
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": type,
            "SubType": subtype,
            "Title": title,
            "CurrentPage": page,
            "Week": week,
            "TmdbId": tmdbid,
            "PersonId": personid,
            "SubTitle": subtitle,
            "Keyword": keyword,
            "Source": source,
            "Filter": filter,
            "FilterConf": ModuleConf.DISCOVER_FILTER_CONF.get(filter) if filter else {},
            "Params": params_dict
        }
    )


@router.get("/ranking", response_class=HTMLResponse)
def ranking_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """排行榜页面"""
    return templates.TemplateResponse(
        request, "discovery/ranking.html",
        {"DiscoveryType": "RANKING"}
    )


@router.get("/douban_movie", response_class=HTMLResponse)
def douban_movie_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": "DOUBANTAG",
            "SubType": "MOV",
            "Title": "豆瓣电影",
            "Filter": "douban_movie",
            "FilterConf": ModuleConf.DISCOVER_FILTER_CONF.get('douban_movie')
        }
    )


@router.get("/douban_tv", response_class=HTMLResponse)
def douban_tv_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": "DOUBANTAG",
            "SubType": "TV",
            "Title": "豆瓣电视剧",
            "Filter": "douban_tv",
            "FilterConf": ModuleConf.DISCOVER_FILTER_CONF.get('douban_tv')
        }
    )


@router.get("/tmdb_movie", response_class=HTMLResponse)
def tmdb_movie_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": "DISCOVER",
            "SubType": "MOV",
            "Title": "TMDB电影",
            "Filter": "tmdb_movie",
            "FilterConf": ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_movie')
        }
    )


@router.get("/tmdb_tv", response_class=HTMLResponse)
def tmdb_tv_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": "DISCOVER",
            "SubType": "TV",
            "Title": "TMDB电视剧",
            "Filter": "tmdb_tv",
            "FilterConf": ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_tv')
        }
    )


@router.get("/bangumi", response_class=HTMLResponse)
def bangumi_page(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/ranking.html",
        {"DiscoveryType": "BANGUMI"}
    )


@router.get("/media_detail", response_class=HTMLResponse)
def media_detail_page(
    request: Request,
    id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/mediainfo.html",
        {"TmdbId": id, "Type": type}
    )


@router.get("/discovery_person", response_class=HTMLResponse)
def discovery_person_page(
    request: Request,
    tmdbid: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    subtitle: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "discovery/person.html",
        {
            "TmdbId": tmdbid,
            "Title": title,
            "SubTitle": subtitle,
            "Type": type,
            "Keyword": keyword
        }
    )


@router.get("/downloaded", response_class=HTMLResponse)
def downloaded_page(
    request: Request,
    page: Optional[str] = Query("1"),
    current_user: str = Depends(get_current_user),
):
    """近期下载页面"""
    return templates.TemplateResponse(
        request, "discovery/recommend.html",
        {
            "Type": "DOWNLOADED",
            "Title": "近期下载",
            "CurrentPage": page
        }
    )
