"""
Site Repository
Handles site configuration and statistics related database operations.
"""
import json
import time

from sqlalchemy import cast, Integer, func

from app.db import DbPersist
from app.db.models import CONFIGSITE, SITEUSERINFOSTATS, SITEFAVICON, SITEUSERSEEDINGINFO, SITESTATISTICSHISTORY
from app.db.repositories.base_repository import BaseRepository


class SiteRepository(BaseRepository):
    """
    站点仓储
    处理站点配置、统计、图标、做种数据的数据库操作
    """

    # ==================== Site Configuration ====================

    def get_config_site(self):
        """
        查询所有站点信息
        """
        return self._db.query(CONFIGSITE).order_by(cast(CONFIGSITE.PRI, Integer).asc()).all()

    def get_site_by_id(self, tid):
        """
        查询1个站点信息
        """
        return self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).all()

    @DbPersist(BaseRepository._db)
    def insert_config_site(self, name, site_pri, rssurl=None, signurl=None, cookie=None, note=None, rss_uses=None):
        """
        插入站点信息
        """
        if not name:
            return
        self._db.insert(CONFIGSITE(
            NAME=name,
            PRI=site_pri,
            RSSURL=rssurl,
            SIGNURL=signurl,
            COOKIE=cookie,
            NOTE=note,
            INCLUDE=rss_uses
        ))

    @DbPersist(BaseRepository._db)
    def delete_config_site(self, tid):
        """
        删除站点信息
        """
        if not tid:
            return
        self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).delete()

    @DbPersist(BaseRepository._db)
    def update_config_site(self, tid, name, site_pri, rssurl, signurl, cookie, note, rss_uses):
        """
        更新站点信息
        """
        if not tid:
            return
        self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).update({
            "NAME": name,
            "PRI": site_pri,
            "RSSURL": rssurl,
            "SIGNURL": signurl,
            "COOKIE": cookie,
            "NOTE": note,
            "INCLUDE": rss_uses
        })

    @DbPersist(BaseRepository._db)
    def update_config_site_note(self, tid, note):
        """
        更新站点属性
        """
        if not tid:
            return
        self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).update({"NOTE": note})

    @DbPersist(BaseRepository._db)
    def update_site_cookie_ua(self, tid, cookie, ua=None):
        """
        更新站点Cookie和ua
        """
        if not tid:
            return
        rec = self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).first()
        if rec.NOTE:
            note = json.loads(rec.NOTE)
            if ua:
                note['ua'] = ua
        else:
            note = {}
        self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).update({
            "COOKIE": cookie,
            "NOTE": json.dumps(note)
        })

    @DbPersist(BaseRepository._db)
    def update_site_rssurl(self, tid, rssurl):
        """
        更新站点rssurl
        """
        if not tid:
            return
        self._db.query(CONFIGSITE).filter(CONFIGSITE.ID == int(tid)).update({"RSSURL": rssurl})

    # ==================== Site User Statistics ====================

    @DbPersist(BaseRepository._db)
    def update_site_user_statistics_site_name(self, new_name, old_name):
        """
        更新站点用户数据中站点名称
        """
        self._db.query(SITEUSERINFOSTATS).filter(SITEUSERINFOSTATS.SITE == old_name).update({
            "SITE": new_name
        })

    @DbPersist(BaseRepository._db)
    def update_site_user_statistics(self, site_user_infos: list):
        """
        更新站点用户粒度数据
        """
        if not site_user_infos:
            return
        update_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

        for site_user_info in site_user_infos:
            site = site_user_info.site_name
            username = site_user_info.username
            user_level = site_user_info.user_level
            join_at = site_user_info.join_at
            upload = site_user_info.upload
            download = site_user_info.download
            ratio = site_user_info.ratio
            seeding = site_user_info.seeding
            seeding_size = site_user_info.seeding_size
            leeching = site_user_info.leeching
            bonus = site_user_info.bonus
            url = site_user_info.site_url
            msg_unread = site_user_info.message_unread

            if not self.is_exists_site_user_statistics(url):
                self._db.insert(SITEUSERINFOSTATS(
                    SITE=site,
                    USERNAME=username,
                    USER_LEVEL=user_level,
                    JOIN_AT=join_at,
                    UPDATE_AT=update_at,
                    UPLOAD=upload,
                    DOWNLOAD=download,
                    RATIO=ratio,
                    SEEDING=seeding,
                    LEECHING=leeching,
                    SEEDING_SIZE=seeding_size,
                    BONUS=bonus,
                    URL=url,
                    MSG_UNREAD=msg_unread
                ))
            else:
                self._db.query(SITEUSERINFOSTATS).filter(SITEUSERINFOSTATS.URL == url).update({
                    "SITE": site,
                    "USERNAME": username,
                    "USER_LEVEL": user_level,
                    "JOIN_AT": join_at,
                    "UPDATE_AT": update_at,
                    "UPLOAD": upload,
                    "DOWNLOAD": download,
                    "RATIO": ratio,
                    "SEEDING": seeding,
                    "LEECHING": leeching,
                    "SEEDING_SIZE": seeding_size,
                    "BONUS": bonus,
                    "MSG_UNREAD": msg_unread
                })

    def is_exists_site_user_statistics(self, url):
        """
        判断站点数据是否存在
        使用first()代替count()提高性能
        """
        if not url:
            return False
        return self._db.query(SITEUSERINFOSTATS).filter(SITEUSERINFOSTATS.URL == url).first() is not None

    def is_site_user_statistics_exists(self, url):
        """
        判断站点用户数据是否存在
        """
        if not url:
            return False
        return self._db.query(SITEUSERINFOSTATS).filter(SITEUSERINFOSTATS.URL == url).first() is not None

    def get_site_user_statistics(self, num=100, strict_urls=None):
        """
        查询站点数据历史
        """
        if strict_urls:
            return self._db.query(SITEUSERINFOSTATS) \
                .join(CONFIGSITE, SITEUSERINFOSTATS.SITE == CONFIGSITE.NAME) \
                .filter(SITEUSERINFOSTATS.URL.in_(tuple(strict_urls + ["__DUMMY__"]))) \
                .order_by(cast(CONFIGSITE.PRI, Integer).asc()).limit(num).all()
        else:
            return self._db.query(SITEUSERINFOSTATS).limit(num).all()

    # ==================== Site Favicon ====================

    @DbPersist(BaseRepository._db)
    def update_site_favicon(self, site_user_infos: list):
        """
        更新站点图标数据
        """
        if not site_user_infos:
            return

        for site_user_info in site_user_infos:
            site_icon = "data:image/ico;base64," + \
                        site_user_info.site_favicon if site_user_info.site_favicon else site_user_info.site_url + "/favicon.ico"

            if not self.is_exists_site_favicon(site_user_info.site_name):
                self._db.insert(SITEFAVICON(
                    SITE=site_user_info.site_name,
                    URL=site_user_info.site_url,
                    FAVICON=site_icon
                ))
            elif site_user_info.site_favicon:
                self._db.query(SITEFAVICON).filter(SITEFAVICON.SITE == site_user_info.site_name).update({
                    "URL": site_user_info.site_url,
                    "FAVICON": site_icon
                })

    def is_exists_site_favicon(self, site):
        """
        判断站点图标是否存在
        """
        count = self._db.query(SITEFAVICON).filter(SITEFAVICON.SITE == site).count()
        return count > 0

    def get_site_favicons(self, site=None):
        """
        查询站点图标数据
        """
        if site:
            return self._db.query(SITEFAVICON).filter(SITEFAVICON.SITE == site).all()
        else:
            return self._db.query(SITEFAVICON).all()

    # ==================== Site Seeding Info ====================

    @DbPersist(BaseRepository._db)
    def update_site_seed_info_site_name(self, new_name, old_name):
        """
        更新站点做种数据中站点名称
        """
        self._db.query(SITEUSERSEEDINGINFO).filter(SITEUSERSEEDINGINFO.SITE == old_name).update({
            "SITE": new_name
        })

    @DbPersist(BaseRepository._db)
    def update_site_seed_info(self, site_user_infos: list):
        """
        更新站点做种数据
        """
        if not site_user_infos:
            return
        update_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

        for site_user_info in site_user_infos:
            if not self.is_site_seeding_info_exist(url=site_user_info.site_url):
                self._db.insert(SITEUSERSEEDINGINFO(
                    SITE=site_user_info.site_name,
                    UPDATE_AT=update_at,
                    SEEDING_INFO=site_user_info.seeding_info,
                    URL=site_user_info.site_url
                ))
            else:
                self._db.query(SITEUSERSEEDINGINFO).filter(SITEUSERSEEDINGINFO.URL == site_user_info.site_url).update({
                    "SITE": site_user_info.site_name,
                    "UPDATE_AT": update_at,
                    "SEEDING_INFO": site_user_info.seeding_info
                })

    def is_site_seeding_info_exist(self, url):
        """
        判断做种数据是否已存在
        """
        return self._db.query(SITEUSERSEEDINGINFO).filter(
            SITEUSERSEEDINGINFO.URL == url
        ).first() is not None

    def get_site_seeding_info(self, site):
        """
        查询站点做种信息
        """
        return self._db.query(SITEUSERSEEDINGINFO.SEEDING_INFO).filter(
            SITEUSERSEEDINGINFO.SITE == site
        ).first()

    # ==================== Site Statistics History ====================

    def is_site_statistics_history_exists(self, url, date):
        """
        判断站点历史数据是否存在
        """
        if not url or not date:
            return False
        return self._db.query(SITESTATISTICSHISTORY).filter(
            SITESTATISTICSHISTORY.URL == url,
            SITESTATISTICSHISTORY.DATE == date
        ).first() is not None

    @DbPersist(BaseRepository._db)
    def update_site_statistics_site_name(self, new_name, old_name):
        """
        更新站点统计数据中站点名称
        """
        self._db.query(SITESTATISTICSHISTORY).filter(SITESTATISTICSHISTORY.SITE == old_name).update({
            "SITE": new_name
        })

    @DbPersist(BaseRepository._db)
    def insert_site_statistics_history(self, site_user_infos: list):
        """
        插入站点数据
        使用批量插入/更新提高性能
        """
        if not site_user_infos:
            return

        date_now = time.strftime('%Y-%m-%d', time.localtime(time.time()))

        urls = [info.site_url for info in site_user_infos if info.site_url]
        existing_records = {}
        if urls:
            records = self._db.query(SITESTATISTICSHISTORY.URL).filter(
                SITESTATISTICSHISTORY.DATE == date_now,
                SITESTATISTICSHISTORY.URL.in_(urls)
            ).all()
            existing_records = {r[0] for r in records}

        insert_mappings = []
        update_mappings = []

        for site_user_info in site_user_infos:
            data = {
                "SITE": site_user_info.site_name,
                "USER_LEVEL": site_user_info.user_level,
                "DATE": date_now,
                "UPLOAD": site_user_info.upload,
                "DOWNLOAD": site_user_info.download,
                "RATIO": site_user_info.ratio,
                "SEEDING": site_user_info.seeding,
                "LEECHING": site_user_info.leeching,
                "SEEDING_SIZE": site_user_info.seeding_size,
                "BONUS": site_user_info.bonus,
                "URL": site_user_info.site_url
            }

            if site_user_info.site_url in existing_records:
                update_mappings.append((site_user_info.site_url, data))
            else:
                insert_mappings.append(data)

        if insert_mappings:
            self._db.bulk_insert_mappings(SITESTATISTICSHISTORY, insert_mappings, batch_size=100)

        for url, data in update_mappings:
            self._db.query(SITESTATISTICSHISTORY).filter(
                SITESTATISTICSHISTORY.DATE == date_now,
                SITESTATISTICSHISTORY.URL == url
            ).update(data)

    def get_site_statistics_history(self, site, days=30):
        """
        查询站点数据历史
        """
        return self._db.query(SITESTATISTICSHISTORY).filter(
            SITESTATISTICSHISTORY.SITE == site
        ).order_by(SITESTATISTICSHISTORY.DATE.asc()).limit(days)

    def get_site_statistics_recent_sites(self, days=7, end_day=None, strict_urls=None):
        """
        查询近期上传下载量
        """
        import datetime

        if strict_urls is None:
            strict_urls = []
        end = datetime.datetime.now()
        if end_day:
            try:
                end = datetime.datetime.strptime(end_day, "%Y-%m-%d")
            except Exception:
                pass

        b_date = (end - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        e_date = end.strftime("%Y-%m-%d")

        date_ret = self._db.query(
            func.max(SITESTATISTICSHISTORY.DATE),
            func.min(SITESTATISTICSHISTORY.DATE)
        ).filter(
            SITESTATISTICSHISTORY.DATE > b_date,
            SITESTATISTICSHISTORY.DATE <= e_date
        ).all()

        if date_ret and date_ret[0][0]:
            total_upload = 0
            total_download = 0
            ret_site_uploads = []
            ret_site_downloads = []
            min_date = date_ret[0][1]
            max_date = date_ret[0][0]

            if strict_urls:
                subquery = self._db.query(
                    SITESTATISTICSHISTORY.SITE.label("SITE"),
                    SITESTATISTICSHISTORY.DATE.label("DATE"),
                    func.sum(SITESTATISTICSHISTORY.UPLOAD).label("UPLOAD"),
                    func.sum(SITESTATISTICSHISTORY.DOWNLOAD).label("DOWNLOAD")
                ).filter(
                    SITESTATISTICSHISTORY.DATE >= min_date,
                    SITESTATISTICSHISTORY.DATE <= max_date,
                    SITESTATISTICSHISTORY.URL.in_(tuple(strict_urls + ["__DUMMY__"]))
                ).group_by(SITESTATISTICSHISTORY.SITE, SITESTATISTICSHISTORY.DATE).subquery()
            else:
                subquery = self._db.query(
                    SITESTATISTICSHISTORY.SITE.label("SITE"),
                    SITESTATISTICSHISTORY.DATE.label("DATE"),
                    func.sum(SITESTATISTICSHISTORY.UPLOAD).label("UPLOAD"),
                    func.sum(SITESTATISTICSHISTORY.DOWNLOAD).label("DOWNLOAD")
                ).filter(
                    SITESTATISTICSHISTORY.DATE >= min_date,
                    SITESTATISTICSHISTORY.DATE <= max_date
                ).group_by(SITESTATISTICSHISTORY.SITE, SITESTATISTICSHISTORY.DATE).subquery()

            rets = self._db.query(
                subquery.c.SITE,
                func.min(subquery.c.UPLOAD),
                func.min(subquery.c.DOWNLOAD),
                func.max(subquery.c.UPLOAD),
                func.max(subquery.c.DOWNLOAD)
            ).group_by(subquery.c.SITE).all()

            ret_sites = []
            for ret_b in rets:
                ret_b = list(ret_b)
                if ret_b[1] == 0 and ret_b[2] == 0:
                    ret_b[1] = ret_b[3]
                    ret_b[2] = ret_b[4]
                ret_sites.append(ret_b[0])
                if int(ret_b[1]) < int(ret_b[3]):
                    total_upload += int(ret_b[3]) - int(ret_b[1])
                    ret_site_uploads.append(int(ret_b[3]) - int(ret_b[1]))
                else:
                    ret_site_uploads.append(0)
                if int(ret_b[2]) < int(ret_b[4]):
                    total_download += int(ret_b[4]) - int(ret_b[2])
                    ret_site_downloads.append(int(ret_b[4]) - int(ret_b[2]))
                else:
                    ret_site_downloads.append(0)

            return total_upload, total_download, ret_sites, ret_site_uploads, ret_site_downloads
        else:
            return 0, 0, [], [], []

    def get_site_daily_history(self, days=30, end_day=None, strict_urls=None):
        """
        查询各站点每日上传量（按站点、按天分组，返回增量）
        """
        import datetime

        if strict_urls is None:
            strict_urls = []
        end = datetime.datetime.now()
        if end_day:
            try:
                end = datetime.datetime.strptime(end_day, "%Y-%m-%d")
            except Exception:
                pass

        b_date = (end - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        e_date = end.strftime("%Y-%m-%d")

        # 按站点、日期分组，取每天的上传/下载总量
        query = self._db.query(
            SITESTATISTICSHISTORY.SITE,
            SITESTATISTICSHISTORY.DATE,
            func.sum(SITESTATISTICSHISTORY.UPLOAD).label("UPLOAD"),
            func.sum(SITESTATISTICSHISTORY.DOWNLOAD).label("DOWNLOAD")
        ).filter(
            SITESTATISTICSHISTORY.DATE > b_date,
            SITESTATISTICSHISTORY.DATE <= e_date
        )

        if strict_urls:
            query = query.filter(SITESTATISTICSHISTORY.URL.in_(tuple(strict_urls + ["__DUMMY__"])))

        results = query.group_by(
            SITESTATISTICSHISTORY.SITE,
            SITESTATISTICSHISTORY.DATE
        ).order_by(
            SITESTATISTICSHISTORY.DATE.asc()
        ).all()

        if not results:
            return {"dates": [], "series": []}

        # 按站点组织数据
        site_data: dict = {}
        all_dates = set()
        for row in results:
            site_name, date_str, upload, download = row
            all_dates.add(date_str)
            if site_name not in site_data:
                site_data[site_name] = {}
            site_data[site_name][date_str] = {
                "upload": int(upload or 0),
                "download": int(download or 0),
            }

        sorted_dates = sorted(all_dates)

        # 计算每日增量
        series = []
        for site_name in sorted(site_data.keys()):
            uploads = []
            downloads = []
            prev_up = None
            prev_down = None
            for d in sorted_dates:
                val = site_data[site_name].get(d)
                if val is None:
                    # 当天无数据：增量为0，prev保持不变（避免下一天被0拉偏）
                    uploads.append(0)
                    downloads.append(0)
                    continue
                up = val["upload"]
                down = val["download"]
                # 前值必须 > 0 才计算增量，避免首次数据/默认值 0 导致跳变
                if prev_up is not None and prev_up > 0 and up >= prev_up:
                    inc_up = up - prev_up
                else:
                    inc_up = 0
                if prev_down is not None and prev_down > 0 and down >= prev_down:
                    inc_down = down - prev_down
                else:
                    inc_down = 0
                uploads.append(inc_up)
                downloads.append(inc_down)
                prev_up = up
                prev_down = down
            series.append({
                "name": site_name,
                "upload": uploads,
                "download": downloads,
            })

        return {"dates": sorted_dates, "series": series}
