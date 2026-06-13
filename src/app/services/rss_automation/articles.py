"""RSS 文章操作（模块级函数）."""

import traceback
from typing import Any

import log
from app.core.exceptions import RepositoryError, ServiceError
from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.services.rss_automation.executor import _parse_userrss_result
from app.utils import ExceptionUtils, StringUtils


def _get_rss_articles(service, taskid: int | None) -> Any:
    """查看自定义RSS报文."""
    if not taskid:
        return
    rss_articles = []
    taskinfo = service.get_rsstask_info(taskid)
    if not taskinfo:
        return
    rss_result = _parse_userrss_result(service, taskinfo)
    if len(rss_result) == 0:
        return []
    for res in rss_result:
        try:
            title = res.get("title")
            if not title:
                continue
            enclosure = res.get("enclosure")
            link = res.get("link")
            description = res.get("description")
            size = StringUtils.str_filesize(res.get("size"))
            date = StringUtils.unify_datetime_str(res.get("date")) or ""
            year = res.get("year")
            if year and len(year) > 4:
                year = year[:4]
            finish_flag = service.is_article_processed(taskinfo.get("uses"), title, year, enclosure)
            params = {
                "title": title,
                "link": link,
                "enclosure": enclosure,
                "size": size,
                "description": description,
                "date": date,
                "finish_flag": finish_flag,
                "year": year,
                "address_index": res.get("address_index"),
            }
            if params not in rss_articles:
                rss_articles.append(params)
        except (ServiceError, RepositoryError):
            raise
        except Exception as e:
            ExceptionUtils.exception_traceback(e, "获取RSS报文时发生错误")
            log.error(f"[RssTaskService]获取RSS报文发生错误：{str(e)} - {traceback.format_exc()}")
    return sorted(rss_articles, key=lambda x: x["date"], reverse=True)


def _test_rss_articles(service, taskid: int | None, title: str) -> tuple[Any, bool, bool] | None:
    """测试RSS报文."""
    taskinfo = service.get_rsstask_info(taskid)
    if not taskinfo:
        return
    media_info = service.media.get_media_info(title=title)
    if not media_info:
        log.warn(f"[RssTaskService]{title} 识别媒体信息出错！")
        return None
    filter_args = {
        "include": taskinfo.get("include"),
        "exclude": taskinfo.get("exclude"),
        "rule": taskinfo.get("filter") if taskinfo.get("uses") == "D" else None,
    }
    match_flag, res_order, match_msg = service.filter.check_torrent_filter(
        meta_info=media_info, filter_args=filter_args
    )
    if not match_flag:
        log.info(f"[RssTaskService]{match_msg}")
    else:
        log.info(
            f"[RssTaskService]{title} 识别为 {media_info.get_title_string()} {media_info.get_season_episode_string()} 匹配成功"
        )
    media_info.set_torrent_info(res_order=res_order)
    no_exists = {}
    exist_flag = False
    if not media_info.tmdb_id:
        log.info(f"[RssTaskService]{title} 识别为 {media_info.get_name()} 未匹配到媒体信息")
    else:
        if media_info.type == MediaType.MOVIE:
            exist_flag, no_exists, _ = service.downloader.check_exists_medias(meta_info=media_info, no_exists=no_exists)
            if exist_flag:
                log.info(f"[RssTaskService]电影 {media_info.get_title_string()} 已存在")
        else:
            exist_flag, no_exists, _ = service.downloader.check_exists_medias(meta_info=media_info, no_exists=no_exists)
            if exist_flag:
                if not no_exists or not no_exists.get(media_info.tmdb_id):
                    log.info(
                        f"[RssTaskService]电视剧 {media_info.get_title_string()} {media_info.get_season_episode_string()} 已存在"
                    )
            if no_exists.get(media_info.tmdb_id):
                log.info(
                    f"[RssTaskService]{media_info.get_title_string()} 缺失季集：{no_exists.get(media_info.tmdb_id)}"
                )
    return media_info, match_flag, exist_flag


def _check_rss_articles(service, taskid: int | None, flag: str, articles: list[dict]) -> bool:
    """RSS报文处理设置."""
    try:
        task_type = service.get_rsstask_info(taskid).get("uses")
        if flag == "set_finished":
            for article in articles:
                title = article.get("title")
                enclosure = article.get("enclosure")
                year = article.get("year")
                meta_name = f"{title} {year}" if year else title
                if not service.is_article_processed(task_type, title or "", enclosure, year):
                    if task_type == "D":
                        service.rsshelper.simple_insert_rss_torrents(meta_name, enclosure)
                    elif task_type == "R":
                        service.rsshelper.simple_insert_rss_torrents(meta_name, meta_name)
        elif flag == "set_unfinish":
            for article in articles:
                title = article.get("title")
                enclosure = article.get("enclosure")
                year = article.get("year")
                meta_name = f"{title} {year}" if year else title
                if task_type == "D":
                    service.rsshelper.simple_delete_rss_torrents(meta_name, enclosure)
                elif task_type == "R":
                    service.rsshelper.simple_delete_rss_torrents(meta_name, meta_name)
        else:
            return False
        return True
    except (ServiceError, RepositoryError):
        raise
    except Exception as e:
        ExceptionUtils.exception_traceback(e, "设置RSS报文状态时发生错误")
        log.error(f"[RssTaskService]设置RSS报文状态时发生错误：{str(e)} - {traceback.format_exc()}")
        return False


def _download_rss_articles(service, taskid: int | None, articles: list[dict]) -> bool | None:
    """RSS报文下载."""
    if not taskid:
        return
    taskinfo = service.get_rsstask_info(taskid)
    if not taskinfo:
        return
    for article in articles:
        media = service.media.get_media_info(title=article.get("title"))
        if not media:
            log.warn(f"[RssTaskService]{article.get('title')} 识别媒体信息出错！")
            continue
        media.set_torrent_info(enclosure=article.get("enclosure"))
        downloader_id, ret, ret_msg = service.downloader.download(
            media_info=media,
            download_dir=taskinfo.get("save_path"),
            download_setting=taskinfo.get("download_setting"),
            in_from=SearchType.USERRSS,
            proxy=taskinfo.get("proxy"),
        )
        conf = service.downloader.get_downloader_conf(downloader_id)
        downloader_name = conf.get("name") if conf else ""
        if ret:
            service.rsshelper.insert_rss_torrents(media)
            service.config_repo.insert_userrss_task_history(taskid or 0, media.org_string or "", downloader_name or "")
        else:
            log.error(
                "[RssTaskService]添加下载任务 {} 失败：{}".format(
                    media.get_title_string(), ret_msg or "请检查下载任务是否已存在"
                )
            )
            return False
    return True
