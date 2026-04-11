import json
import os.path


from flask_login import current_user

import log
from app.downloader import Downloader
from app.filetransfer import FileTransfer
from app.indexer import Indexer
from app.media import Media
from app.media.meta import MetaInfo
from app.searcher import Searcher
from app.sites import Sites
from app.torrentremover import TorrentRemover
from app.utils import SystemUtils, ExceptionUtils, Torrent
from app.utils.types import SearchType
from app.utils.temp_manager import temp_manager
from web.actions._base import WebActionBase


class WebActionDownloadMixin:
    @staticmethod
    def _download(data):
        """
        从WEB添加下载
        """
        dl_id = data.get("id")
        dl_dir = data.get("dir")
        dl_setting = data.get("setting")
        results = Searcher().get_search_result_by_id(dl_id)
        for res in results:
            enclosure = ''
            # 处理m-tem下载链接
            if ('m-team' in res.PAGEURL or 'yemapt' in res.PAGEURL) and res.ENCLOSURE is None:
                enclosure = Downloader().get_download_url(res.PAGEURL)
            else:
                enclosure = res.ENCLOSURE
            media = Media().get_media_info(title=res.TORRENT_NAME, subtitle=res.DESCRIPTION)
            if not media:
                continue
            media.set_torrent_info(enclosure=enclosure,
                                   size=res.SIZE,
                                   site=res.SITE,
                                   page_url=res.PAGEURL,
                                   upload_volume_factor=float(
                                       res.UPLOAD_VOLUME_FACTOR),
                                   download_volume_factor=float(res.DOWNLOAD_VOLUME_FACTOR))
            # 添加下载
            _, ret, ret_msg = Downloader().download(media_info=media,
                                                    download_dir=dl_dir,
                                                    download_setting=dl_setting,
                                                    in_from=SearchType.WEB,
                                                    user_name=current_user.username)
            if not ret:
                return WebActionBase._fail(code=-1, msg=ret_msg)
        return WebActionBase._success(msg="")

    @staticmethod
    def _download_link(data):
        """
        从WEB添加下载链接
        """
        site = data.get("site")
        enclosure = data.get("enclosure")
        title = data.get("title")
        description = data.get("description")
        page_url = data.get("page_url")
        # 处理m-tem下载链接
        if ('m-team' in page_url or 'yemapt' in page_url) and (enclosure == 'None' or enclosure == ''):
            enclosure = Downloader().get_download_url(page_url)
        size = data.get("size")
        seeders = data.get("seeders")
        uploadvolumefactor = data.get("uploadvolumefactor")
        downloadvolumefactor = data.get("downloadvolumefactor")
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        if not title or not enclosure:
            return WebActionBase._fail(code=-1, msg="种子信息有误")
        media = Media().get_media_info(title=title, subtitle=description)
        media.site = site
        media.enclosure = enclosure
        media.page_url = page_url
        media.size = size
        media.upload_volume_factor = float(uploadvolumefactor)
        media.download_volume_factor = float(downloadvolumefactor)
        media.seeders = seeders
        # 添加下载
        _, ret, ret_msg = Downloader().download(media_info=media,
                                                download_dir=dl_dir,
                                                download_setting=dl_setting,
                                                in_from=SearchType.WEB,
                                                user_name=current_user.username)
        if not ret:
            return WebActionBase._fail(msg=ret_msg or "如连接正常，请检查下载任务是否存在")
        return WebActionBase._success(msg="下载成功")

    @staticmethod
    def _download_torrent(data):
        """
        从种子文件或者URL链接添加下载
        files：文件地址的列表，urls：种子链接地址列表或者单个链接地址
        """
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        files = data.get("files") or []
        urls = data.get("urls") or []
        if not files and not urls:
            return WebActionBase._fail(code=-1, msg="没有种子文件或者种子链接")
        # 下载种子
        uploaded_files = []
        for file_item in files:
            if not file_item:
                continue
            file_name = file_item.get("upload", {}).get("filename")
            file_path = temp_manager.get_temp_path(file_name)
            uploaded_files.append(file_path)
            media_info = Media().get_media_info(title=file_name)
            if media_info:
                media_info.site = "WEB"
            # 添加下载
            Downloader().download(media_info=media_info,
                                  download_dir=dl_dir,
                                  download_setting=dl_setting,
                                  torrent_file=file_path,
                                  in_from=SearchType.WEB,
                                  user_name=current_user.username)
        # 清理上传的临时文件
        for tmp_file in uploaded_files:
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
                    log.debug(f"【Web】已删除上传的临时文件: {tmp_file}")
            except Exception as e:
                log.warn(f"【Web】删除上传的临时文件失败: {tmp_file}, {str(e)}")
        # 下载链接
        if urls and not isinstance(urls, list):
            urls = [urls]
        for url in urls:
            if not url:
                continue
            # 查询站点
            site_info = Sites().get_sites(siteurl=url)
            if not url.startswith("magnet:"):
                # 下载种子文件，并读取信息
                file_path, _, _, _, retmsg = Torrent().get_torrent_info(
                    url=url,
                    cookie=site_info.get("cookie"),
                    ua=site_info.get("ua"),
                    proxy=site_info.get("proxy")
                )

                if not file_path:
                    return WebActionBase._fail(code=-1, msg=f"下载种子文件失败： {retmsg}")

                media_info = Media().get_media_info(title=os.path.basename(file_path))
                if media_info:
                    media_info.site = "WEB"

            else:
                media_info = MetaInfo('')
                media_info.enclosure = url
                file_path = None

            # 添加下载
            Downloader().download(media_info=media_info,
                                  download_dir=dl_dir,
                                  download_setting=dl_setting,
                                  torrent_file=file_path,
                                  in_from=SearchType.WEB,
                                  user_name=current_user.username)

        return WebActionBase._success(msg="添加下载完成！")

    @staticmethod
    def _pt_start(data):
        """
        开始下载
        """
        tid = data.get("id")
        if id:
            Downloader().start_torrents(ids=tid)
        return WebActionBase._success(id=tid)

    @staticmethod
    def _pt_stop(data):
        """
        停止下载
        """
        tid = data.get("id")
        if id:
            Downloader().stop_torrents(ids=tid)
        return WebActionBase._success(id=tid)

    @staticmethod
    def _pt_remove(data):
        """
        删除下载
        """
        tid = data.get("id")
        if id:
            Downloader().delete_torrents(ids=tid, delete_file=True)
        return WebActionBase._success(id=tid)

    @staticmethod
    def _pt_info(data):
        """
        查询具体种子的信息
        """
        ids = data.get("ids")
        torrents = Downloader().get_downloading_progress(ids=ids)
        return WebActionBase._success(torrents=torrents)

    @staticmethod
    def _get_download_setting(data):
        sid = data.get("sid")
        if sid:
            download_setting = Downloader().get_download_setting(sid=sid)
        else:
            download_setting = list(
                Downloader().get_download_setting().values())
        return WebActionBase._success(data=download_setting)

    @staticmethod
    def _update_download_setting(data):
        sid = data.get("sid")
        name = data.get("name")
        category = data.get("category")
        tags = data.get("tags")
        is_paused = data.get("is_paused")
        upload_limit = data.get("upload_limit")
        download_limit = data.get("download_limit")
        ratio_limit = data.get("ratio_limit")
        seeding_time_limit = data.get("seeding_time_limit")
        downloader = data.get("downloader")
        Downloader().update_download_setting(sid=sid,
                                             name=name,
                                             category=category,
                                             tags=tags,
                                             is_paused=is_paused,
                                             upload_limit=upload_limit or 0,
                                             download_limit=download_limit or 0,
                                             ratio_limit=ratio_limit or 0,
                                             seeding_time_limit=seeding_time_limit or 0,
                                             downloader=downloader)
        return WebActionBase._success()

    @staticmethod
    def _delete_download_setting(data):
        sid = data.get("sid")
        Downloader().delete_download_setting(sid=sid)
        return WebActionBase._success()

    @staticmethod
    def _get_download_dirs(data):
        """
        获取下载目录
        """
        sid = data.get("sid")
        site = data.get("site")
        if not sid and site:
            sid = Sites().get_site_download_setting(site_name=site)
        dirs = Downloader().get_download_dirs(setting=sid)
        return WebActionBase._success(paths=dirs)

    def _update_downloader(self, data):
        """
        更新下载器
        """
        did = data.get("did")
        name = data.get("name")
        dtype = data.get("type")
        enabled = data.get("enabled")
        transfer = data.get("transfer")
        only_nastool = data.get("only_nastool")
        match_path = data.get("match_path")
        rmt_mode = data.get("rmt_mode")
        config = data.get("config")
        if not isinstance(config, str):
            config = json.dumps(config)
        download_dir = data.get("download_dir")
        if not isinstance(download_dir, str):
            download_dir = json.dumps(download_dir)
        Downloader().update_downloader(did=did,
                                       name=name,
                                       dtype=dtype,
                                       enabled=enabled,
                                       transfer=transfer,
                                       only_nastool=only_nastool,
                                       match_path=match_path,
                                       rmt_mode=rmt_mode,
                                       config=config,
                                       download_dir=download_dir)
        return self._success()

    @staticmethod
    def _del_downloader(data):
        """
        删除下载器
        """
        did = data.get("did")
        Downloader().delete_downloader(did=did)
        return WebActionBase._success()

    @staticmethod
    def _check_downloader(data):
        """
        检查下载器
        """
        did = data.get("did")
        if not did:
            return WebActionBase._fail()
        checked = data.get("checked")
        flag = data.get("flag")
        enabled, transfer, only_nastool, match_path = None, None, None, None
        if flag == "enabled":
            enabled = 1 if checked else 0
        elif flag == "transfer":
            transfer = 1 if checked else 0
        elif flag == "only_nastool":
            only_nastool = 1 if checked else 0
        elif flag == "match_path":
            match_path = 1 if checked else 0
        Downloader().check_downloader(did=did,
                                      enabled=enabled,
                                      transfer=transfer,
                                      only_nastool=only_nastool,
                                      match_path=match_path)
        return WebActionBase._success()

    @staticmethod
    def _get_downloaders(data):
        """
        获取下载器
        """
        did = data.get("did")
        return WebActionBase._success(detail=Downloader().get_downloader_conf(did=did))

    @staticmethod
    def _test_downloader(data):
        """
        测试下载器
        """
        dtype = data.get("type")
        config = json.loads(data.get("config"))
        res = Downloader().get_status(dtype=dtype, config=config)
        if res:
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def _find_hardlinks(data):
        files = data.get("files")
        file_dir = data.get("dir")
        if not files:
            return []
        if not file_dir and os.name != "nt":
            # 取根目录下一级为查找目录
            file_dir = os.path.commonpath(files).replace("\\", "/")
            if file_dir != "/":
                file_dir = "/" + str(file_dir).split("/")[1]
            else:
                return []
        hardlinks = {}
        if files:
            try:
                for file in files:
                    hardlinks[os.path.basename(file)] = SystemUtils(
                    ).find_hardlinks(file=file, fdir=file_dir)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return WebActionBase._fail()
        return WebActionBase._success(data=hardlinks)

    @staticmethod
    def _get_indexers():
        """
        获取索引器
        """
        return WebActionBase._success(indexers=Indexer().get_user_indexer_dict())

    @staticmethod
    def _get_indexer_statistics():
        """
        获取索引器统计数据
        """
        dataset = [["indexer", "avg"]]
        result = Indexer().get_indexer_statistics() or []
        dataset.extend([[ret[0], round(ret[4], 1)] for ret in result])
        return WebActionBase._success(data=[{
                "name": ret[0],
                "total": ret[1],
                "fail": ret[2],
                "success": ret[3],
                "avg": round(ret[4], 1),
            } for ret in result], dataset=dataset)

    @staticmethod
    def get_downloading():
        """
        查询正在下载的任务
        """
        MediaHander = Media()
        DownloaderHandler = Downloader()
        torrents = DownloaderHandler.get_downloading_progress()
        for torrent in torrents:
            # 先查询下载记录，没有再识别
            name = torrent.get("name")
            download_info = DownloaderHandler.get_download_history_by_downloader(
                downloader=DownloaderHandler.default_downloader_id,
                download_id=torrent.get("id")
            )
            if download_info:
                name = download_info.TITLE
                year = download_info.YEAR
                poster_path = download_info.POSTER
                se = download_info.SE
            else:
                media_info = MediaHander.get_media_info(title=name)
                if not media_info:
                    torrent.update({
                        "title": name,
                        "image": ""
                    })
                    continue
                year = media_info.year
                name = media_info.title or media_info.get_name()
                se = media_info.get_season_episode_string()
                poster_path = media_info.get_poster_image()
            # 拼装标题
            if year:
                title = "%s (%s) %s" % (name,
                                        year,
                                        se)
            else:
                title = "%s %s" % (name, se)

            torrent.update({
                "title": title,
                "image": poster_path or ""
            })

        return WebActionBase._success(result=torrents)

    @staticmethod
    def _update_torrent_remove_task(data):
        """
        更新自动删种任务
        """
        flag, msg = TorrentRemover().update_torrent_remove_task(data=data)
        if not flag:
            return WebActionBase._fail(msg=msg)
        else:
            return WebActionBase._success()

    @staticmethod
    def _get_torrent_remove_task(data=None):
        """
        获取自动删种任务
        """
        if data:
            tid = data.get("tid")
        else:
            tid = None
        return WebActionBase._success(detail=TorrentRemover().get_torrent_remove_tasks(taskid=tid))

    @staticmethod
    def _delete_torrent_remove_task(data):
        """
        删除自动删种任务
        """
        tid = data.get("tid")
        flag = TorrentRemover().delete_torrent_remove_task(taskid=tid)
        if flag:
            return WebActionBase._success()
        else:
            return WebActionBase._fail()

    @staticmethod
    def _get_remove_torrents(data):
        """
        获取满足自动删种任务的种子
        """
        tid = data.get("tid")
        flag, torrents = TorrentRemover().get_remove_torrents(taskid=tid)
        if not flag or not torrents:
            return WebActionBase._fail(msg="未获取到符合处理条件种子")
        return WebActionBase._success(data=torrents)

    @staticmethod
    def _auto_remove_torrents(data):
        """
        执行自动删种任务
        """
        tid = data.get("tid")
        TorrentRemover().auto_remove_torrents(taskids=tid)
        return WebActionBase._success()

    @staticmethod
    def truncate_blacklist():
        """
        清空文件转移黑名单记录
        """
        FileTransfer().truncate_transfer_blacklist()
        return WebActionBase._success()
