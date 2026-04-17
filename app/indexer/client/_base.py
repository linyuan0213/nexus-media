import datetime
from threading import Lock
import xml.dom.minidom
from abc import ABCMeta, abstractmethod

import log
from app.services.filter_service import FilterService as Filter
from app.helper import ProgressHelper, DbHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.utils import DomUtils, RequestUtils, StringUtils, ExceptionUtils
from app.utils.types import MediaType, SearchType, ProgressKey


class _IIndexClient(metaclass=ABCMeta):
    # 索引器ID
    client_id = ""
    # 索引器类型
    client_type = ""
    # 索引器名称
    client_name = "Indexer"

    media = None
    progress = None
    filter = None
    dbhelper = None
    lock = Lock()

    def __init__(self):
        self.media = Media()
        self.filter = Filter()
        self.progress = ProgressHelper()
        self.dbhelper = DbHelper()
        from app.utils.cache_system import get_cache_manager
        # 统一使用缓存系统的媒体识别缓存，支持 TTL 自动过期
        self.media_ident_cache = get_cache_manager().get_or_create(
            "media_ident", "memory", maxsize=2000, ttl=3600
        )

    @staticmethod
    def _quick_name_match(meta_info, match_media):
        """
        快速名称匹配：不调用TMDB，仅通过名称判断是否可能匹配
        用于过滤搜索结果时跳过大量无效的TMDB查询
        """
        if not meta_info or not match_media:
            return False
        from app.utils import StringUtils

        def _norm(name):
            if not name:
                return ""
            return StringUtils.handler_special_chars(name).upper().strip()

        match_names = {
            _norm(match_media.title),
            _norm(match_media.cn_name),
            _norm(match_media.en_name),
            _norm(match_media.original_title),
        }
        match_names.discard("")

        meta_names = {
            _norm(meta_info.title),
            _norm(meta_info.cn_name),
            _norm(meta_info.en_name),
        }
        meta_names.discard("")

        if not match_names or not meta_names:
            return False

        # 直接相等匹配
        if meta_names & match_names:
            return True

        # 子串匹配（短名称不能作为子串匹配方，避免误匹配）
        for mn in meta_names:
            if len(mn) < 3:
                continue
            for mmn in match_names:
                if len(mmn) < 3:
                    continue
                if mn in mmn or mmn in mn:
                    return True

        return False


    @abstractmethod
    def match(self, ctype):
        """
        匹配实例
        """
        pass

    @abstractmethod
    def get_status(self):
        """
        检查连通性
        """
        pass

    @abstractmethod
    def get_type(self):
        """
        获取类型
        """
        pass

    @abstractmethod
    def get_client_id(self):
        """
        获取索引器id
        """
        pass

    @abstractmethod
    def get_indexers(self):
        """
        :return:  indexer 信息 [(indexerId, indexerName, url)]
        """
        pass

    @abstractmethod
    def search(self, order_seq,
               indexer,
               key_word,
               filter_args: dict,
               match_media,
               in_from: SearchType):
        """
        根据关键字多线程搜索
        """
        if not indexer or not key_word:
            return None
        if filter_args is None:
            filter_args = {}
        # 不在设定搜索范围的站点过滤掉
        if filter_args.get("site") and indexer.name not in filter_args.get("site"):
            return []
        progress_key = ProgressKey.RssSearch if in_from == SearchType.RSS else ProgressKey.Search
        # 计算耗时
        start_time = datetime.datetime.now()
        log.info(f"【{self.index_type}】开始搜索Indexer：{indexer.name} ...")
        # 特殊符号处理
        search_word = StringUtils.handler_special_chars(text=key_word,
                                                        replace_word=" ",
                                                        allow_space=True)
        api_url = f"{indexer.domain}?apikey={self.api_key}&t=search&q={search_word}"
        result_array = self.__parse_torznabxml(api_url)

        # 索引花费时间
        seconds = (datetime.datetime.now() - start_time).seconds
        if len(result_array) == 0:
            with self.lock:
                log.warn(f"【{self.index_type}】{indexer.name} 关键词 {key_word} 未搜索到数据")
                self.progress.update(ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 未搜索到数据")

                self.dbhelper.insert_indexer_statistics(indexer=indexer.name,
                                            itype=self.client_id,
                                            seconds=seconds,
                                            result='N'
                                            )
                return []
        else:
            with self.lock:
                log.warn(f"【{self.index_type}】{indexer.name} 关键词 {key_word} 返回数据：{len(result_array)}")
                # 更新进度
                self.progress.update(ptype=progress_key, text=f"{indexer.name} 关键词 {key_word} 返回 {len(result_array)} 条数据")
                # 索引统计
                self.dbhelper.insert_indexer_statistics(indexer=indexer.name,
                                                        itype=self.client_id,
                                                        seconds=seconds,
                                                        result='Y'
                                                        )
                return self.filter_search_results(result_array=result_array,
                                                order_seq=order_seq,
                                                indexer=indexer,
                                                filter_args=filter_args,
                                                match_media=match_media,
                                                start_time=start_time,
                                                progress_key=progress_key)

    @staticmethod
    def __parse_torznabxml(url):
        """
        从torznab xml中解析种子信息
        :param url: URL地址
        :return: 解析出来的种子信息列表
        """
        if not url:
            return []
        try:
            # 优化：增加超时时间以应对慢响应站点，同时添加更健壮的错误处理
            ret = RequestUtils(timeout=15).get_res(url)
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            return []
        if not ret:
            return []
        xmls = ret.text
        if not xmls:
            return []

        torrents = []
        try:
            # 解析XML
            dom_tree = xml.dom.minidom.parseString(xmls)
            root_node = dom_tree.documentElement
            items = root_node.getElementsByTagName("item")
            for item in items:
                try:
                    # indexer id
                    indexer_id = DomUtils.tag_value(item, "jackettindexer", "id",
                                                    default=DomUtils.tag_value(item, "prowlarrindexer", "id", ""))
                    # indexer
                    indexer = DomUtils.tag_value(item, "jackettindexer",
                                                 default=DomUtils.tag_value(item, "prowlarrindexer", default=""))

                    # 标题
                    title = DomUtils.tag_value(item, "title", default="")
                    if not title:
                        continue
                    # 种子链接
                    enclosure = DomUtils.tag_value(item, "enclosure", "url", default="")
                    if not enclosure:
                        continue
                    # 描述
                    description = DomUtils.tag_value(item, "description", default="")
                    # 种子大小
                    size = DomUtils.tag_value(item, "size", default=0)
                    # 种子页面
                    page_url = DomUtils.tag_value(item, "comments", default="")

                    # 做种数
                    seeders = 0
                    # 下载数
                    peers = 0
                    # 是否免费
                    freeleech = False
                    # 下载因子
                    downloadvolumefactor = 1.0
                    # 上传因子
                    uploadvolumefactor = 1.0
                    # imdbid
                    imdbid = ""

                    torznab_attrs = item.getElementsByTagName("torznab:attr")
                    for torznab_attr in torznab_attrs:
                        name = torznab_attr.getAttribute('name')
                        value = torznab_attr.getAttribute('value')
                        if name == "seeders":
                            seeders = value
                        if name == "peers":
                            peers = value
                        if name == "downloadvolumefactor":
                            downloadvolumefactor = value
                            if float(downloadvolumefactor) == 0:
                                freeleech = True
                        if name == "uploadvolumefactor":
                            uploadvolumefactor = value
                        if name == "imdbid":
                            imdbid = value

                    tmp_dict = {'indexer_id': indexer_id,
                                'indexer': indexer,
                                'title': title,
                                'enclosure': enclosure,
                                'description': description,
                                'size': size,
                                'seeders': seeders,
                                'peers': peers,
                                'freeleech': freeleech,
                                'downloadvolumefactor': downloadvolumefactor,
                                'uploadvolumefactor': uploadvolumefactor,
                                'page_url': page_url,
                                'imdbid': imdbid}
                    torrents.append(tmp_dict)
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    continue
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            pass

        return torrents

    def filter_search_results(self, result_array: list,
                              order_seq,
                              indexer,
                              filter_args: dict,
                              match_media,
                              start_time,
                              progress_key=ProgressKey.Search):
        """
        从搜索结果中匹配符合资源条件的记录
        采用三阶段模式优化 TMDB 查询：
        1. 第一阶段：本地轻量级过滤，收集需要 TMDB 识别的候选
        2. 第二阶段：并发查询 TMDB
        3. 第三阶段：TMDB 匹配及后续过滤
        """
        ret_array = []
        index_sucess = 0
        index_rule_fail = 0
        index_match_fail = 0
        index_error = 0

        # ---------- 第一阶段：本地轻量级过滤 ----------
        candidates = []
        for item in result_array:
            torrent_name = item.get('title')
            description = item.get('description')
            if not torrent_name:
                index_error += 1
                continue
            enclosure = item.get('enclosure')
            size = item.get('size')
            seeders = item.get('seeders')
            peers = item.get('peers')
            page_url = item.get('page_url')
            uploadvolumefactor = round(float(item.get('uploadvolumefactor')), 1) if item.get(
                'uploadvolumefactor') is not None else 1.0
            downloadvolumefactor = round(float(item.get('downloadvolumefactor')), 1) if item.get(
                'downloadvolumefactor') is not None else 1.0
            imdbid = item.get("imdbid")
            labels = item.get("labels")

            # 做种数过滤
            if filter_args.get("seeders") and not indexer.public and str(seeders) == "0":
                log.info(f"【{self.client_name}】{torrent_name} 做种数为0")
                index_rule_fail += 1
                continue

            # 解析种子名称
            meta_info = MetaInfo(title=torrent_name, subtitle=f"{labels} {description}")
            if not meta_info.get_name():
                log.info(f"【{self.client_name}】{torrent_name} 无法识别到名称")
                index_match_fail += 1
                continue

            # 大小及促销等
            meta_info.set_torrent_info(size=size,
                                       imdbid=imdbid,
                                       upload_volume_factor=uploadvolumefactor,
                                       download_volume_factor=downloadvolumefactor,
                                       labels=labels)

            # 类型过滤
            if meta_info.type == MediaType.TV and filter_args.get("type") == MediaType.MOVIE:
                log.info(
                    f"【{self.client_name}】{torrent_name} 是 {meta_info.type.value}，"
                    f"不匹配类型：{filter_args.get('type').value}")
                index_rule_fail += 1
                continue

            # 规则过滤
            match_flag, res_order, match_msg = self.filter.check_torrent_filter(
                meta_info=meta_info,
                filter_args=filter_args,
                uploadvolumefactor=uploadvolumefactor,
                downloadvolumefactor=downloadvolumefactor)
            if not match_flag:
                log.info(f"【{self.client_name}】{match_msg}")
                index_rule_fail += 1
                continue

            if not match_media:
                # 不过滤，直接命中
                media_info = meta_info
                media_info.set_torrent_info(site=indexer.name,
                                            site_order=order_seq,
                                            enclosure=enclosure,
                                            res_order=res_order,
                                            filter_rule=filter_args.get("rule"),
                                            size=size,
                                            seeders=seeders,
                                            peers=peers,
                                            description=description,
                                            page_url=page_url,
                                            upload_volume_factor=uploadvolumefactor,
                                            download_volume_factor=downloadvolumefactor)
                if media_info not in ret_array:
                    index_sucess += 1
                    ret_array.append(media_info)
                else:
                    index_rule_fail += 1
                continue

            # IMDBID 直接匹配
            if meta_info.imdb_id and match_media.imdb_id and str(meta_info.imdb_id) == str(match_media.imdb_id):
                candidates.append({
                    "item": item,
                    "meta_info": meta_info,
                    "res_order": res_order,
                    "skip_tmdb": True,
                    "media_info": self.media.merge_media_info(meta_info, match_media),
                })
                continue

            # 快速名称匹配
            if self._quick_name_match(meta_info, match_media):
                log.debug(f"【{self.client_name}】{torrent_name} 快速名称匹配成功，跳过TMDB查询")
                candidates.append({
                    "item": item,
                    "meta_info": meta_info,
                    "res_order": res_order,
                    "skip_tmdb": True,
                    "media_info": self.media.merge_media_info(meta_info, match_media),
                })
                continue

            # 需要 TMDB 查询
            candidates.append({
                "item": item,
                "meta_info": meta_info,
                "res_order": res_order,
                "skip_tmdb": False,
                "media_info": None,
            })

        # ---------- 第二阶段：并发 TMDB 查询 ----------
        if candidates:
            to_identify = []
            seen_names = set()
            for cand in candidates:
                if cand["skip_tmdb"]:
                    continue
                meta_info = cand["meta_info"]
                # 用解析后的名称作为缓存键，大幅提高同一剧集不同集数/质量的缓存命中率
                cache_key = meta_info.get_name() or cand["item"].get("title")
                if not cache_key or self.media_ident_cache.get(cache_key) is not None or cache_key in seen_names:
                    continue
                seen_names.add(cache_key)
                to_identify.append((cache_key, cand["item"].get("description")))

            if to_identify:
                from concurrent.futures import ThreadPoolExecutor
                log.info(f"【{self.client_name}】并发识别 {len(to_identify)} 条不重复结果 ...")

                def _do_identify(args):
                    name, desc = args
                    try:
                        return name, self.media.get_media_info(title=name, subtitle=desc, chinese=False)
                    except Exception as e:
                        log.error(f"【{self.client_name}】识别出错: {name}, {e}")
                        return name, None

                # 限制并发数，避免对 TMDB 造成过大压力导致限流或超时，
                # 同时防止过多线程并发占用数据库连接池（get_media_info 内部亦有线程池）
                max_workers = min(len(to_identify), 4)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for name, media_info in executor.map(_do_identify, to_identify):
                        if media_info:
                            self.media_ident_cache.set(name, media_info)

        # ---------- 第三阶段：TMDB 匹配及后续过滤 ----------
        for cand in candidates:
            item = cand["item"]
            meta_info = cand["meta_info"]
            res_order = cand["res_order"]
            torrent_name = item.get("title")
            description = item.get("description")
            size = item.get("size")
            seeders = item.get("seeders")
            peers = item.get("peers")
            page_url = item.get("page_url")
            uploadvolumefactor = round(float(item.get("uploadvolumefactor")), 1) if item.get(
                "uploadvolumefactor") is not None else 1.0
            downloadvolumefactor = round(float(item.get("downloadvolumefactor")), 1) if item.get(
                "downloadvolumefactor") is not None else 1.0
            enclosure = item.get("enclosure")

            if cand["skip_tmdb"]:
                media_info = cand["media_info"]
            else:
                cache_key = meta_info.get_name() or torrent_name
                media_info = self.media_ident_cache.get(cache_key)
                if media_info is not None:
                    log.debug(f"【{self.client_name}】从缓存获取媒体信息: {cache_key}")
                else:
                    media_info = None

                if not media_info:
                    log.warn(f"【{self.client_name}】{cache_key} 识别媒体信息出错！")
                    index_error += 1
                    continue
                elif not media_info.tmdb_info:
                    log.info(
                        f"【{self.client_name}】{cache_key} 识别为 {media_info.get_name()} 未匹配到媒体信息")
                    index_match_fail += 1
                    continue

                # TMDBID 是否匹配
                if str(media_info.tmdb_id) != str(match_media.tmdb_id):
                    log.info(
                        f"【{self.client_name}】{cache_key} 识别为 "
                        f"{media_info.type.value}/{media_info.get_title_string()}/{media_info.tmdb_id} "
                        f"与 {match_media.type.value}/{match_media.get_title_string()}/{match_media.tmdb_id} 不匹配")
                    index_match_fail += 1
                    continue

                # 合并媒体数据
                media_info = self.media.merge_media_info(media_info, match_media)

            # 过滤类型
            if filter_args.get("type"):
                if (filter_args.get("type") == MediaType.TV and media_info.type == MediaType.MOVIE) \
                        or (filter_args.get("type") == MediaType.MOVIE and media_info.type == MediaType.TV):
                    log.info(
                        f"【{self.client_name}】{cache_key if not cand['skip_tmdb'] else torrent_name} 是 {media_info.type.value}/"
                        f"{media_info.tmdb_id}，不是 {filter_args.get('type').value}")
                    index_rule_fail += 1
                    continue

            # 洗版
            display_name = cache_key if not cand["skip_tmdb"] else torrent_name
            if match_media.over_edition:
                if media_info.type != MediaType.MOVIE and media_info.get_episode_list():
                    log.info(f"【{self.client_name}】"
                             f"{media_info.get_title_string()}{media_info.get_season_string()} "
                             f"正在洗版，过滤掉季集不完整的资源：{display_name} {description}")
                    continue
                if match_media.res_order and int(res_order) <= int(match_media.res_order):
                    log.info(
                        f"【{self.client_name}】"
                        f"{media_info.get_title_string()}{media_info.get_season_string()} "
                        f"正在洗版，已洗版优先级：{100 - int(match_media.res_order)}，"
                        f"当前资源优先级：{100 - int(res_order)}，"
                        f"跳过低优先级或同优先级资源：{display_name}"
                    )
                    continue

            # 检查标题是否匹配季、集、年
            if not self.filter.is_torrent_match_sey(media_info,
                                                    filter_args.get("season"),
                                                    filter_args.get("episode"),
                                                    filter_args.get("year")):
                log.info(
                    f"【{self.client_name}】{display_name} 识别为 {media_info.type.value}/"
                    f"{media_info.get_title_string()}/{media_info.get_season_episode_string()} 不匹配季/集/年份")
                index_match_fail += 1
                continue

            # 匹配到了
            log.info(
                f"【{self.client_name}】{display_name} {description} 识别为 {media_info.get_title_string()} "
                f"{media_info.get_season_episode_string()} 匹配成功")
            media_info.set_torrent_info(site=indexer.name,
                                        site_order=order_seq,
                                        enclosure=enclosure,
                                        res_order=res_order,
                                        filter_rule=filter_args.get("rule"),
                                        size=size,
                                        seeders=seeders,
                                        peers=peers,
                                        description=description,
                                        page_url=page_url,
                                        upload_volume_factor=uploadvolumefactor,
                                        download_volume_factor=downloadvolumefactor)
            if media_info not in ret_array:
                index_sucess += 1
                ret_array.append(media_info)
            else:
                index_rule_fail += 1

        # 计算耗时
        end_time = datetime.datetime.now()
        log.info(
            f"【{self.client_name}】{indexer.name} {len(result_array)} 条数据中，"
            f"过滤 {index_rule_fail}，"
            f"不匹配 {index_match_fail}，"
            f"错误 {index_error}，"
            f"有效 {index_sucess}，"
            f"耗时 {(end_time - start_time).seconds} 秒")
        self.progress.update(ptype=progress_key,
                             text=f"{indexer.name} {len(result_array)} 条数据中，"
                                  f"过滤 {index_rule_fail}，"
                                  f"不匹配 {index_match_fail}，"
                                  f"错误 {index_error}，"
                                  f"有效 {index_sucess}，"
                                  f"耗时 {(end_time - start_time).seconds} 秒")
        return ret_array
