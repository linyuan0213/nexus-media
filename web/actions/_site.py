import json


from app.indexer import Indexer
from app.sites import Sites, SiteUserInfo, SiteCookie, SiteConf
from app.utils import StringUtils
from web.cache import cache
from web.actions._base import WebActionBase


class WebActionSiteMixin:
    @staticmethod
    def _update_site(data):
        """
        维护站点信息
        """

        _sites = Sites()

        def _is_site_duplicate(query_name, query_tid):
            # 检查是否重名
            for site in _sites.get_sites_by_name(name=query_name):
                if str(site.get("id")) != str(query_tid):
                    return True
            return False

        tid = data.get('site_id')
        name = data.get('site_name')
        site_pri = data.get('site_pri')
        rssurl = data.get('site_rssurl')
        signurl = data.get('site_signurl')
        cookie = data.get('site_cookie')
        note = data.get('site_note')
        if isinstance(note, dict):
            note = json.dumps(note)
        rss_uses = data.get('site_include')

        if _is_site_duplicate(name, tid):
            return WebActionBase._fail(code=400, msg="站点名称重复")

        if tid:
            sites = _sites.get_sites(siteid=tid)
            # 站点不存在
            if not sites:
                return WebActionBase._fail(code=400, msg="站点不存在")
            old_name = sites.get('name')
            ret = _sites.update_site(tid=tid,
                                     name=name,
                                     site_pri=site_pri,
                                     rssurl=rssurl,
                                     signurl=signurl,
                                     cookie=cookie,
                                     note=note,
                                     rss_uses=rss_uses)
            if ret and (name != old_name):
                # 更新历史站点数据信息
                SiteUserInfo().update_site_name(name, old_name)

        else:
            ret = _sites.add_site(name=name,
                                  site_pri=site_pri,
                                  rssurl=rssurl,
                                  signurl=signurl,
                                  cookie=cookie,
                                  note=note,
                                  rss_uses=rss_uses)

        return WebActionBase._fail(code=ret)

    @staticmethod
    def _get_site(data):
        """
        查询单个站点信息
        """
        tid = data.get("id")
        site_free = False
        site_2xfree = False
        site_hr = False
        if tid:
            ret = Sites().get_sites(siteid=tid)
            if ret.get("signurl"):
                site_attr = SiteConf().get_grap_conf(ret.get("signurl"))
                if site_attr.get("FREE"):
                    site_free = True
                if site_attr.get("2XFREE"):
                    site_2xfree = True
                if site_attr.get("HR"):
                    site_hr = True
        else:
            ret = []
        return WebActionBase._success(site=ret, site_free=site_free, site_2xfree=site_2xfree, site_hr=site_hr)

    @staticmethod
    def _get_sites(data):
        """
        查询多个站点信息
        """
        rss = True if data.get("rss") else False
        brush = True if data.get("brush") else False
        statistic = True if data.get("statistic") else False
        basic = True if data.get("basic") else False
        if basic:
            sites = Sites().get_site_dict(rss=rss,
                                          brush=brush,
                                          statistic=statistic)
        else:
            sites = Sites().get_sites(rss=rss,
                                      brush=brush,
                                      statistic=statistic)
        return WebActionBase._success(sites=sites)

    @staticmethod
    def _del_site(data):
        """
        删除单个站点信息
        """
        tid = data.get("id")
        if tid:
            ret = Sites().delete_site(tid)
            return WebActionBase._fail(code=ret)
        else:
            return WebActionBase._success()

    @staticmethod
    def _test_site(data):
        """
        测试站点连通性
        """
        flag, msg, times = Sites().test_connection(data.get("id"))
        code = 0 if flag else -1
        return WebActionBase._fail(code=code, msg=msg, time=times)

    @staticmethod
    def _get_site_favicon(data):
        """
        获取站点图标
        """
        sitename = data.get("name")
        return WebActionBase._success(icon=Sites().get_site_favicon(site_name=sitename))

    @staticmethod
    def _update_site_cookie_ua(data):
        """
        更新单个站点的Cookie和UA
        """
        siteid = data.get("site_id")
        cookie = data.get("site_cookie")
        ua = data.get("site_ua")
        Sites().update_site_cookie(siteid=siteid, cookie=cookie, ua=ua)
        return WebActionBase._success(messages="请求发送成功")

    @staticmethod
    def _set_site_captcha_code(data):
        """
        设置站点验证码
        """
        code = data.get("code")
        value = data.get("value")
        SiteCookie().set_code(code=code, value=value)
        return WebActionBase._success()

    @staticmethod
    def _check_site_attr(data):
        """
        检查站点标识
        """
        site_attr = SiteConf().get_grap_conf(data.get("url"))
        site_free = site_2xfree = site_hr = False
        if site_attr.get("FREE"):
            site_free = True
        if site_attr.get("2XFREE"):
            site_2xfree = True
        if site_attr.get("HR"):
            site_hr = True
        return WebActionBase._success(site_free=site_free, site_2xfree=site_2xfree, site_hr=site_hr)

    @staticmethod
    def get_site_user_statistics(data):
        """
        获取站点用户统计信息
        """
        sites = data.get("sites")
        encoding = data.get("encoding") or "RAW"
        sort_by = data.get("sort_by")
        sort_on = data.get("sort_on")
        site_hash = data.get("site_hash")
        statistics = SiteUserInfo().get_site_user_statistics(
            sites=sites, encoding=encoding)
        # 修复馒头站点显示
        for item in statistics:
            if 'm-team' in item.get('url'):
                site_info = Sites().get_sites(siteurl=item.get('url'))
                item['url'] = site_info.get('signurl')
        if sort_by and sort_on in ["asc", "desc"]:
            if sort_on == "asc":
                statistics.sort(key=lambda x: x[sort_by])
            else:
                statistics.sort(key=lambda x: x[sort_by], reverse=True)
        if site_hash == "Y":
            for item in statistics:
                item["site_hash"] = StringUtils.md5_hash(item.get("site"))
        return WebActionBase._success(data=statistics)

    @staticmethod
    def _get_site_activity(data):
        """
        查询site活动[上传，下载，魔力值]
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return WebActionBase._fail(msg="查询参数错误")

        resp = {"code": 0}

        resp.update(
            {"dataset": SiteUserInfo().get_pt_site_activity_history(data["name"])})
        return resp

    @staticmethod
    def _get_site_history(data):
        """
        查询site 历史[上传，下载]
        :param data: {"days":累计时间}
        :return:
        """
        cache.delete("statistics")
        if not data or "days" not in data or not isinstance(data["days"], int):
            return WebActionBase._fail(msg="查询参数错误")

        resp = {"code": 0}
        _, _, site, upload, download = SiteUserInfo().get_pt_site_statistics_history(
            data["days"] + 1, data.get("end_day", None)
        )

        # 调整为dataset组织数据
        dataset = [["site", "upload", "download"]]
        dataset.extend([[site, upload, download]
                        for site, upload, download in zip(site, upload, download)])
        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def _get_site_seeding_info(data):
        """
        查询site 做种分布信息 大小，做种数
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return WebActionBase._fail(msg="查询参数错误")

        resp = {"code": 0}

        seeding_info = SiteUserInfo().get_pt_site_seeding_info(
            data["name"]).get("seeding_info", [])
        # 调整为dataset组织数据
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)

        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def list_site_resources(data):
        resources = Indexer().list_resources(index_id=data.get("id"),
                                             page=data.get("page"),
                                             keyword=data.get("keyword"))
        if not resources:
            return WebActionBase._fail(msg="获取站点资源出现错误，无法连接到站点！")
        else:
            return WebActionBase._success(data=resources)
