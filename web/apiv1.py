from flask import Blueprint, request
from web.controllers.system import _user_manager as user_manager, _net_test as net_test, _sch as sch, _search as search_func, _version as version, _restart as restart, update_system as update_system, refresh_process as refresh_process, _update_config as update_config, _restory_backup as restory_backup, _set_system_config as set_system_config, _update_message_client as update_message_client, _delete_message_client as delete_message_client, _check_message_client as check_message_client, _get_message_client as get_message_client, _test_message_client as test_message_client
from web.controllers.rbac import get_users as get_users
from web.controllers.media import _name_test as name_test, get_search_result as get_search_result, get_downloaded as get_downloaded, clear_history as clear_history, get_unknown_list as get_unknown_list, get_transfer_history as get_transfer_history, get_transfer_statistics as get_transfer_statistics, _start_mediasync as start_mediasync, _mediasync_state as mediasync_state, get_library_playhistory as get_library_playhistory, get_library_mediacount as get_library_mediacount, get_library_spacesize as get_library_spacesize, _movie_calendar_data as movie_calendar_data, _tv_calendar_data as tv_calendar_data, get_recommend as get_recommend, search_media_infos as search_media_infos, _get_tvseason_list as get_tvseason_list, _media_info as media_info, media_detail as media_detail, _media_similar as media_similar, _media_recommendations as media_recommendations, _person_medias as person_medias, _download_subtitle as download_subtitle
from web.controllers.filter import _rule_test as rule_test, get_filterrules as get_filterrules, _add_filtergroup as add_filtergroup, _restore_filtergroup as restore_filtergroup, _set_default_filtergroup as set_default_filtergroup, _del_filtergroup as del_filtergroup, _add_filterrule as add_filterrule, _del_filterrule as del_filterrule, _filterrule_detail as filterrule_detail, _share_filtergroup as share_filtergroup, _import_filtergroup as import_filtergroup
from web.controllers.site import _update_site as update_site, _get_site as get_site, _get_site_favicon as get_site_favicon, _test_site as test_site, _del_site as del_site, _get_site_activity as get_site_activity, _check_site_attr as check_site_attr, _get_site_history as get_site_history, _get_site_seeding_info as get_site_seeding_info, list_site_resources as list_site_resources, _get_sites as get_sites
from web.controllers.download import _get_indexers as get_indexers, _download as download_download, _download_link as download_link, _pt_start as pt_start, _pt_stop as pt_stop, _pt_info as pt_info, _pt_remove as pt_remove, get_downloading as get_downloading, _get_download_setting as get_download_setting, _update_download_setting as update_download_setting, _delete_download_setting as delete_download_setting, _get_download_dirs as get_download_dirs, _update_downloader as update_downloader, _del_downloader as del_downloader, _get_downloaders as get_downloaders, _check_downloader as check_downloader, _test_downloader as test_downloader, truncate_blacklist as truncate_blacklist, _get_torrent_remove_task as get_torrent_remove_task, _delete_torrent_remove_task as delete_torrent_remove_task, _update_torrent_remove_task as update_torrent_remove_task
from web.controllers.sync import _del_unknown_path as del_unknown_path, _rename as rename, _rename_udf as rename_udf, re_identification as re_identification, delete_history as delete_history, _get_sub_path as get_sub_path, _test_connection as test_connection, _update_directory as update_directory, _add_or_edit_sync_path as add_or_edit_sync_path, get_sync_path as get_sync_path, _delete_sync_path as delete_sync_path, _check_sync_path as check_sync_path, _run_directory_sync as run_directory_sync
from web.controllers.rss import _remove_rss_media as remove_rss_media, _add_rss_media as add_rss_media, _refresh_rss as refresh_rss, _rss_detail as rss_detail, _re_rss_history as re_rss_history, _delete_rss_history as delete_rss_history, get_rss_history as get_rss_history, truncate_rsshistory as truncate_rsshistory, get_movie_rss_list as get_movie_rss_list, get_tv_rss_list as get_tv_rss_list
from web.controllers.userrss import _get_userrss_task as get_userrss_task, _delete_userrss_task as delete_userrss_task, _update_userrss_task as update_userrss_task, _get_rssparser as get_rssparser, _delete_rssparser as delete_rssparser, _update_rssparser as update_rssparser, _list_rss_articles as list_rss_articles, _rss_article_test as rss_article_test, _list_rss_history as list_rss_history, _rss_articles_check as rss_articles_check, _rss_articles_download as rss_articles_download, _list_rss_parsers as list_rss_parsers, _list_rss_tasks as list_rss_tasks
from web.controllers.words import get_categories as get_categories, _add_custom_word_group as add_custom_word_group, _delete_custom_word_group as delete_custom_word_group, _add_or_edit_custom_word as add_or_edit_custom_word, _get_custom_word as get_custom_word, _delete_custom_words as delete_custom_words, _check_custom_words as check_custom_words, _export_custom_words as export_custom_words, _analyse_import_custom_words_code as analyse_import_custom_words_code, _import_custom_words as import_custom_words, get_customwords as get_customwords
from web.controllers.brush import _add_brushtask as add_brushtask, _del_brushtask as del_brushtask, _brushtask_detail as brushtask_detail, _list_brushtask_torrents as list_brushtask_torrents, _run_brushtask as run_brushtask, _list_brushtasks as list_brushtasks
from web.controllers.plugin import install_plugin as install_plugin, uninstall_plugin as uninstall_plugin, get_plugin_apps as get_plugin_apps, get_plugins_conf as get_plugins_conf, get_plugin_state as get_plugin_state
from flask_restx import Api, reqparse, Resource

from app.utils import TokenCache
from config import Config
from web.backend.user import User
from web.controllers.site import get_site_user_statistics
from web.security import generate_access_token

apiv1_bp = Blueprint("apiv1",
                     __name__,
                     static_url_path='',
                     static_folder='./frontend/static/',
                     template_folder='./frontend/', )
Apiv1 = Api(apiv1_bp,
            version="1.0",
            title="NAStool Api",
            description="POST接口调用 /user/login 获取Token，GET接口使用 基础设置->安全->Api Key 调用",
            doc="/",
            security='Bearer Auth',
            authorizations={"Bearer Auth": {"type": "apiKey", "name": "Authorization", "in": "header"}},
            )
# API分组
user = Apiv1.namespace('user', description='用户')
system = Apiv1.namespace('system', description='系统')
config = Apiv1.namespace('config', description='设置')
site = Apiv1.namespace('site', description='站点')
service = Apiv1.namespace('service', description='服务')
subscribe = Apiv1.namespace('subscribe', description='订阅')
rss = Apiv1.namespace('rss', description='自定义RSS')
recommend = Apiv1.namespace('recommend', description='推荐')
search = Apiv1.namespace('search', description='搜索')
download = Apiv1.namespace('download', description='下载')
organization = Apiv1.namespace('organization', description='整理')
torrentremover = Apiv1.namespace('torrentremover', description='自动删种')
library = Apiv1.namespace('library', description='媒体库')
brushtask = Apiv1.namespace('brushtask', description='刷流')
media = Apiv1.namespace('media', description='媒体')
sync = Apiv1.namespace('sync', description='目录同步')
filterrule = Apiv1.namespace('filterrule', description='过滤规则')
words = Apiv1.namespace('words', description='识别词')
message = Apiv1.namespace('message', description='消息通知')
plugin = Apiv1.namespace('plugin', description='插件')


class ApiResource(Resource):
    """
    API 入口（认证已下沉到 Controller 的 @any_auth）
    """
    method_decorators = []


class ClientResource(Resource):
    """
    客户端入口（认证已下沉到 Controller 的 @any_auth）
    """
    method_decorators = []


def Failed():
    """
    返回失败报名
    """
    return {
        "code": -1,
        "success": False,
        "data": {}
    }


@user.route('/login')
class UserLogin(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('username', type=str, help='用户名', location='form', required=True)
    parser.add_argument('password', type=str, help='密码', location='form', required=True)

    @user.doc(parser=parser)
    def post(self):
        """
        用户登录
        """
        args = self.parser.parse_args()
        username = args.get('username')
        password = args.get('password')
        if not username or not password:
            return {"code": 1, "success": False, "message": "用户名或密码错误"}
        user_info = User().get_user(username)
        if not user_info:
            return {"code": 1, "success": False, "message": "用户名或密码错误"}
        # 校验密码
        if not user_info.verify_password(password):
            return {"code": 1, "success": False, "message": "用户名或密码错误"}
        # 缓存Token
        token = generate_access_token(username)
        apikey = Config().get_config("security").get("api_key")
        TokenCache.set(apikey, token)
        return {
            "code": 0,
            "success": True,
            "data": {
                "token": token,
                "apikey": apikey,
                "userinfo": {
                    "userid": user_info.id,
                    "username": user_info.username,
                    "userpris": str(user_info.pris).split(",")
                }
            }
        }


@user.route('/info')
class UserInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('username', type=str, help='用户名', location='form', required=True)

    @user.doc(parser=parser)
    def post(self):
        """
        获取用户信息
        """
        args = self.parser.parse_args()
        username = args.get('username')
        user_info = User().get_user(username)
        if not user_info:
            return {"code": 1, "success": False, "message": "用户名不正确"}
        return {
            "code": 0,
            "success": True,
            "data": {
                "userid": user_info.id,
                "username": user_info.username,
                "userpris": str(user_info.pris).split(",")
            }
        }


@user.route('/manage')
class UserManage(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('oper', type=str, help='操作类型（add 新增/del删除）', location='form', required=True)
    parser.add_argument('name', type=str, help='用户名', location='form', required=True)
    parser.add_argument('pris', type=str, help='权限', location='form')

    @user.doc(parser=parser)
    def post(self):
        """
        用户管理
        """
        return user_manager(self.parser.parse_args())


@user.route('/list')
class UserList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有用户
        """
        return get_users({})


@service.route('/mediainfo')
class ServiceMediaInfo(ApiResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='args', required=True)

    @service.doc(parser=parser)
    def get(self):
        """
        识别媒体信息（密钥认证）
        """
        return name_test(self.parser.parse_args())


@service.route('/name/test')
class ServiceNameTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        名称识别测试
        """
        return name_test(self.parser.parse_args())


@service.route('/rule/test')
class ServiceRuleTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('title', type=str, help='名称', location='form', required=True)
    parser.add_argument('subtitle', type=str, help='描述', location='form')
    parser.add_argument('size', type=float, help='大小（GB）', location='form')

    @service.doc(parser=parser)
    def post(self):
        """
        过滤规则测试
        """
        return rule_test(self.parser.parse_args())


@service.route('/network/test')
class ServiceNetworkTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='URL地址', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        网络连接性测试
        """
        return net_test(self.parser.parse_args().get("url"))


@service.route('/run')
class ServiceRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('item', type=str,
                        help='服务名称（pttransfer、sync、rssdownload、subscribe_search_all）',
                        location='form',
                        required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        运行服务
        """
        return sch(self.parser.parse_args())


@site.route('/statistics')
class SiteStatistic(ApiResource):
    @staticmethod
    def get():
        """
        获取站点数据明细（密钥认证）
        """
        # 返回站点信息
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_statistics": get_site_user_statistics({"encoding": "DICT"}).get("data")
            }
        }


@site.route('/sites')
class SiteSites(ApiResource):
    @staticmethod
    def get():
        """
        获取所有站点配置（密钥认证）
        """
        result = get_sites({})
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_sites": result.get("sites")
            }
        }


@site.route('/update')
class SiteUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('site_name', type=str, help='站点名称', location='form', required=True)
    parser.add_argument('site_id', type=int, help='更新站点ID', location='form')
    parser.add_argument('site_pri', type=str, help='优先级', location='form')
    parser.add_argument('site_rssurl', type=str, help='RSS地址', location='form')
    parser.add_argument('site_signurl', type=str, help='站点地址', location='form')
    parser.add_argument('site_cookie', type=str, help='Cookie', location='form')
    parser.add_argument('site_note', type=str, help='站点属性', location='form')
    parser.add_argument('site_include', type=str, help='站点用途', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        新增/删除站点
        """
        return update_site(self.parser.parse_args())


@site.route('/info')
class SiteInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询单个站点详情
        """
        return get_site(self.parser.parse_args())


@site.route('/favicon')
class SiteFavicon(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        获取站点图标(Base64)
        """
        return get_site_favicon(self.parser.parse_args())


@site.route('/test')
class SiteTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        测试站点连通性
        """
        return test_site(self.parser.parse_args())


@site.route('/delete')
class SiteDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        删除站点
        """
        return del_site(self.parser.parse_args())


@site.route('/statistics/activity')
class SiteStatisticsActivity(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点 上传/下载/做种数据
        """
        return get_site_activity(self.parser.parse_args())


@site.route('/check')
class SiteCheck(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='站点地址', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        检查站点是否支持FREE/HR检测
        """
        return check_site_attr(self.parser.parse_args())


@site.route('/statistics/history')
class SiteStatisticsHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('days', type=int, help='时间范围（天）', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询所有站点历史数据
        """
        return get_site_history(self.parser.parse_args())


@site.route('/statistics/seedinfo')
class SiteStatisticsSeedinfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点做种分布
        """
        return get_site_seeding_info(self.parser.parse_args())


@site.route('/resources')
class SiteResources(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='站点索引ID', location='form', required=True)
    parser.add_argument('page', type=int, help='页码', location='form')
    parser.add_argument('keyword', type=str, help='站点名称', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点资源列表
        """
        return list_site_resources(self.parser.parse_args())


@site.route('/list')
class SiteList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('basic', type=int, help='只查询基本信息（0-否/1-是）', location='form')
    parser.add_argument('rss', type=int, help='订阅（0-否/1-是）', location='form')
    parser.add_argument('brush', type=int, help='刷流（0-否/1-是）', location='form')
    parser.add_argument('statistic', type=int, help='数据统计（0-否/1-是）', location='form')

    def post(self):
        """
        查询站点列表
        """
        return get_sites(self.parser.parse_args())


@site.route('/indexers')
class SiteIndexers(ClientResource):

    @staticmethod
    def post():
        """
        查询站点索引列表
        """
        return get_indexers({})


@search.route('/keyword')
class SearchKeyword(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('search_word', type=str, help='搜索关键字', location='form', required=True)
    parser.add_argument('unident', type=int, help='快速模式（0-否/1-是）', location='form')
    parser.add_argument('filters', type=str, help='过滤条件', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('media_type', type=str, help='类型（电影/电视剧）', location='form')

    @search.doc(parser=parser)
    def post(self):
        """
        根据关键字/TMDBID搜索
        """
        return search_func(self.parser.parse_args())


@search.route('/result')
class SearchResult(ClientResource):
    @staticmethod
    def post():
        """
        查询搜索结果
        """
        return get_search_result({})


@download.route('/search')
class DownloadSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='搜索结果ID', location='form', required=True)
    parser.add_argument('dir', type=str, help='保存目录', location='form')
    parser.add_argument('setting', type=str, help='下载设置', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下载搜索结果
        """
        return download_download(self.parser.parse_args())


@download.route('/item')
class DownloadItem(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('enclosure', type=str, help='链接URL', location='form', required=True)
    parser.add_argument('title', type=str, help='标题', location='form', required=True)
    parser.add_argument('site', type=str, help='站点名称', location='form')
    parser.add_argument('description', type=str, help='描述', location='form')
    parser.add_argument('page_url', type=str, help='详情页面URL', location='form')
    parser.add_argument('size', type=str, help='大小', location='form')
    parser.add_argument('seeders', type=str, help='做种数', location='form')
    parser.add_argument('uploadvolumefactor', type=float, help='上传因子', location='form')
    parser.add_argument('downloadvolumefactor', type=float, help='下载因子', location='form')
    parser.add_argument('dl_dir', type=str, help='保存目录', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下载链接
        """
        return download_link(self.parser.parse_args())


@download.route('/start')
class DownloadStart(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        开始下载任务
        """
        return pt_start(self.parser.parse_args())


@download.route('/stop')
class DownloadStop(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        暂停下载任务
        """
        return pt_stop(self.parser.parse_args())


@download.route('/info')
class DownloadInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ids', type=str, help='任务IDS', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载进度
        """
        return pt_info(self.parser.parse_args())


@download.route('/remove')
class DownloadRemove(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        删除下载任务
        """
        return pt_remove(self.parser.parse_args())


@download.route('/history')
class DownloadHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=str, help='第几页', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载历史
        """
        return get_downloaded(self.parser.parse_args())


@download.route('/now')
class DownloadNow(ClientResource):
    @staticmethod
    def post():
        """
        查询正在下载的任务
        """
        return get_downloading({})


@download.route('/config/info')
class DownloadConfigInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载设置
        """
        return get_download_setting(self.parser.parse_args())


@download.route('/config/update')
class DownloadConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('category', type=str, help='分类', location='form')
    parser.add_argument('tags', type=str, help='标签', location='form')
    parser.add_argument('is_paused', type=int, help='动作（0-添加后开始/1-添加后暂停）', location='form')
    parser.add_argument('upload_limit', type=int, help='上传速度限制', location='form')
    parser.add_argument('download_limit', type=int, help='下载速度限制', location='form')
    parser.add_argument('ratio_limit', type=int, help='分享率限制', location='form')
    parser.add_argument('seeding_time_limit', type=int, help='做种时间限制', location='form')
    parser.add_argument('downloader', type=str, help='下载器（Qbittorrent/Transmission）', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        新增/修改下载设置
        """
        return update_download_setting(self.parser.parse_args())


@download.route('/config/delete')
class DownloadConfigDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        删除下载设置
        """
        return delete_download_setting(self.parser.parse_args())


@download.route('/config/list')
class DownloadConfigList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='ID', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载设置
        """
        return get_download_setting(self.parser.parse_args())


@download.route('/config/directory')
class DownloadConfigDirectory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载保存目录
        """
        return get_download_dirs(self.parser.parse_args())


@download.route('/client/add')
class DownloadClientAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('did', type=str, help='下载器ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（qbittorrent/transmission）', location='form', required=True)
    parser.add_argument('enabled', type=str, help='状态（0-停用 1-启动）', location='form', required=True)
    parser.add_argument('transfer', type=str, help='监控（0-停用 1-启动）', location='form', required=True)
    parser.add_argument('only_nastool', type=str, help='隔离（0-停用 1-启动）', location='form', required=True)
    parser.add_argument('rmt_mode', type=str, help='转移方式', location='form', required=True)
    parser.add_argument('config', type=str, help='配置数据（JSON）', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        新增/修改下载器
        """
        return update_downloader(self.parser.parse_args())


@download.route('/client/delete')
class DownloadClientDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('did', type=str, help='下载器ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        删除下载器
        """
        return del_downloader(self.parser.parse_args())


@download.route('/client/list')
class DownloadClientList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('did', type=str, help='下载器ID', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载器
        """
        return get_downloaders(self.parser.parse_args())


@download.route('/client/check')
class DownloadClientCheck(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('did', type=str, help='下载器ID', location='form', required=True)
    parser.add_argument('checked', type=str, help='状态（0-关闭 1-开启）', location='form', required=True)
    parser.add_argument('flag', type=str, help='标识（enabled transfer only_nastool）', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        设置下载器状态
        """
        return check_downloader(self.parser.parse_args())


@download.route('/client/test')
class DownloadClientTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（qbittorrent/transmission）', location='form', required=True)
    parser.add_argument('config', type=str, help='配置数据（JSON）', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        测试下载器
        """
        return test_downloader(self.parser.parse_args())


@organization.route('/unknown/delete')
class UnknownDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='未识别记录ID', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        删除未识别记录
        """
        return del_unknown_path(self.parser.parse_args())


@organization.route('/unknown/rename')
class UnknownRename(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('logid', type=str, help='转移历史记录ID', location='form')
    parser.add_argument('unknown_id', type=str, help='未识别记录ID', location='form')
    parser.add_argument('syncmod', type=str, help='转移模式', location='form', required=True)
    parser.add_argument('tmdb', type=int, help='TMDB ID', location='form')
    parser.add_argument('title', type=str, help='标题', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('type', type=str, help='类型（MOV/TV/ANIME）', location='form')
    parser.add_argument('season', type=int, help='季号', location='form')
    parser.add_argument('episode_format', type=str, help='集数定位', location='form')
    parser.add_argument('min_filesize', type=int, help='最小文件大小', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        手动识别
        """
        return rename(self.parser.parse_args())


@organization.route('/unknown/renameudf')
class UnknownRenameUDF(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('inpath', type=str, help='源目录', location='form', required=True)
    parser.add_argument('outpath', type=str, help='目的目录', location='form', required=True)
    parser.add_argument('syncmod', type=str, help='转移模式', location='form', required=True)
    parser.add_argument('tmdb', type=int, help='TMDB ID', location='form')
    parser.add_argument('title', type=str, help='标题', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('type', type=str, help='类型（MOV/TV/ANIME）', location='form')
    parser.add_argument('season', type=int, help='季号', location='form')
    parser.add_argument('episode_format', type=str, help='集数定位', location='form')
    parser.add_argument('episode_details', type=str, help='集数范围', location='form')
    parser.add_argument('episode_offset', type=str, help='集数偏移', location='form')
    parser.add_argument('min_filesize', type=int, help='最小文件大小', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        自定义识别
        """
        return rename_udf(self.parser.parse_args())


@organization.route('/unknown/redo')
class UnknownRedo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='类型（unknow/history）', location='form', required=True)
    parser.add_argument('ids', type=list, help='记录ID', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        重新识别
        """
        return re_identification(self.parser.parse_args())


@organization.route('/history/delete')
class TransferHistoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('logids', type=list, help='记录IDS', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        删除媒体整理历史记录
        """
        return delete_history(self.parser.parse_args())


@organization.route('/history/clear')
class TransferHistoryClear(ClientResource):
    def post(self):
        """
        删除媒体整理历史记录
        """
        return clear_history({})


@organization.route('/unknown/list')
class TransferUnknownList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有未识别记录
        """
        return get_unknown_list({})


@organization.route('/history/list')
class TransferHistoryList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, help='页码', location='form', required=True)
    parser.add_argument('pagenum', type=int, help='每页条数', location='form', required=True)
    parser.add_argument('keyword', type=str, help='过滤关键字', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        查询媒体整理历史记录
        """
        return get_transfer_history(self.parser.parse_args())


@organization.route('/history/statistics')
class HistoryStatistics(ClientResource):

    @staticmethod
    def post():
        """
        查询转移历史统计数据
        """
        return get_transfer_statistics({})


@organization.route('/cache/empty')
class TransferCacheEmpty(ClientResource):

    @staticmethod
    def post():
        """
        清空文件转移缓存
        """
        return truncate_blacklist({})


@library.route('/sync/start')
class LibrarySyncStart(ClientResource):

    @staticmethod
    def post():
        """
        开始媒体库同步
        """
        return start_mediasync({})


@library.route('/sync/status')
class LibrarySyncStatus(ClientResource):

    @staticmethod
    def post():
        """
        查询媒体库同步状态
        """
        return mediasync_state({})


@library.route('/mediaserver/playhistory')
class LibraryPlayHistory(ClientResource):

    @staticmethod
    def post():
        """
        查询媒体库播放历史
        """
        return get_library_playhistory({})


@library.route('/mediaserver/statistics')
class LibraryStatistics(ClientResource):

    @staticmethod
    def post():
        """
        查询媒体库统计数据
        """
        return get_library_mediacount({})


@library.route('/space')
class LibrarySpace(ClientResource):

    @staticmethod
    def post():
        """
        查询媒体库存储空间
        """
        return get_library_spacesize({})


@system.route('/version')
class SystemVersion(ClientResource):

    @staticmethod
    def post():
        """
        查询最新版本号
        """
        return version({})


@system.route('/path')
class SystemPath(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('dir', type=str, help='路径', location='form', required=True)
    parser.add_argument('filter', type=str,
                        help='过滤器（ONLYFILE/ONLYDIR/MEDIAFILE/SUBFILE/AUDIOTRACKFILE/ALL）',
                        location='form',
                        required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        查询目录的子目录/文件
        """
        return get_sub_path(self.parser.parse_args())


@system.route('/restart')
class SystemRestart(ClientResource):

    @staticmethod
    def post():
        """
        重启
        """
        return restart({})


@system.route('/update')
class SystemUpdate(ClientResource):

    @staticmethod
    def post():
        """
        升级
        """
        return update_system({})


@system.route('/logout')
class SystemLogout(ClientResource):

    @staticmethod
    def post():
        """
        注销
        """
        token = request.headers.get("Authorization", default=None)
        if token:
            TokenCache.delete(token)
        return {
            "code": 0,
            "success": True
        }


@system.route('/progress')
class SystemProgress(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（ProgressKey）', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        查询搜索/媒体同步等进度
        """
        return refresh_process(self.parser.parse_args())


@config.route('/update')
class ConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('items', type=dict, help='配置项', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        新增/修改配置
        """
        return update_config(self.parser.parse_args().get("items"))


@config.route('/test')
class ConfigTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('command', type=str, help='测试命令', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        测试配置连通性
        """
        return test_connection(self.parser.parse_args())


@config.route('/restore')
class ConfigRestore(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('file_name', type=str, help='备份文件名', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        恢复备份的配置
        """
        return restory_backup(self.parser.parse_args())


@config.route('/info')
class ConfigInfo(ClientResource):
    @staticmethod
    def post():
        """
        获取所有配置文件信息
        """
        return {
            "code": 0,
            "success": True,
            "data": Config().get_config()
        }


@config.route('/directory')
class ConfigDirectory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('oper', type=str, help='操作类型（add/sub/set）', location='form', required=True)
    parser.add_argument('key', type=str, help='配置项', location='form', required=True)
    parser.add_argument('value', type=str, help='配置值', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        配置媒体库目录
        """
        return update_directory(self.parser.parse_args())


@config.route('/set')
class ConfigSet(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('key', type=str, help='配置项', location='form', required=True)
    parser.add_argument('value', type=str, help='配置值', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        保存系统配置值
        """
        return set_system_config(self.parser.parse_args())


@subscribe.route('/delete')
class SubscribeDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='form')
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form')
    parser.add_argument('year', type=str, help='发行年份', location='form')
    parser.add_argument('season', type=int, help='季号', location='form')
    parser.add_argument('rssid', type=int, help='已有订阅ID', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        删除订阅
        """
        return remove_rss_media(self.parser.parse_args())


@subscribe.route('/add')
class SubscribeAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('year', type=str, help='发行年份', location='form')
    parser.add_argument('keyword', type=str, help='自定义搜索词', location='form')
    parser.add_argument('season', type=int, help='季号', location='form')
    parser.add_argument('rssid', type=int, help='已有订阅ID', location='form')
    parser.add_argument('mediaid', type=str, help='TMDBID/DB:豆瓣ID', location='form')
    parser.add_argument('fuzzy_match', type=int, help='模糊匹配（0-否/1-是）', location='form')
    parser.add_argument('rss_sites', type=str, help='RSS站点（,号分隔）', location='form')
    parser.add_argument('search_sites', type=str, help='搜索站点（,号分隔）', location='form')
    parser.add_argument('over_edition', type=int, help='洗版（0-否/1-是）', location='form')
    parser.add_argument('filter_restype', type=str, help='资源类型', location='form')
    parser.add_argument('filter_pix', type=str, help='分辨率', location='form')
    parser.add_argument('filter_team', type=str, help='字幕组/发布组', location='form')
    parser.add_argument('filter_rule', type=int, help='过滤规则', location='form')
    parser.add_argument('download_setting', type=int, help='下载设置', location='form')
    parser.add_argument('save_path', type=str, help='保存路径', location='form')
    parser.add_argument('total_ep', type=int, help='总集数', location='form')
    parser.add_argument('current_ep', type=int, help='开始集数', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        新增/修改订阅
        """
        return add_rss_media(self.parser.parse_args())


@subscribe.route('/movie/date')
class SubscribeMovieDate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='TMDBID/DB:豆瓣ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        电影上映日期
        """
        return movie_calendar_data(self.parser.parse_args())


@subscribe.route('/tv/date')
class SubscribeTVDate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='TMDBID/DB:豆瓣ID', location='form', required=True)
    parser.add_argument('season', type=int, help='季号', location='form', required=True)
    parser.add_argument('name', type=str, help='名称', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        电视剧上映日期
        """
        return tv_calendar_data(self.parser.parse_args())


@subscribe.route('/search')
class SubscribeSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('rssid', type=int, help='订阅ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        订阅刷新搜索
        """
        return refresh_rss(self.parser.parse_args())


@subscribe.route('/info')
class SubscribeInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='订阅ID', location='form', required=True)
    parser.add_argument('type', type=str, help='订阅类型（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        订阅详情
        """
        return rss_detail(self.parser.parse_args())


@subscribe.route('/redo')
class SubscribeRedo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='订阅历史ID', location='form', required=True)
    parser.add_argument('type', type=str, help='订阅类型（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        历史重新订阅
        """
        return re_rss_history(self.parser.parse_args())


@subscribe.route('/history/delete')
class SubscribeHistoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='订阅ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        删除订阅历史
        """
        return delete_rss_history(self.parser.parse_args())


@subscribe.route('/history')
class SubscribeHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        查询订阅历史
        """
        return get_rss_history(self.parser.parse_args())


@subscribe.route('/cache/delete')
class SubscribeCacheDelete(ClientResource):
    @staticmethod
    def post():
        """
        清理订阅缓存
        """
        return truncate_rsshistory({})


@subscribe.route('/movie/list')
class SubscribeMovieList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有电影订阅
        """
        return get_movie_rss_list({})


@subscribe.route('/tv/list')
class SubscribeTvList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有电视剧订阅
        """
        return get_tv_rss_list({})


@recommend.route('/list')
class RecommendList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型', location='form', required=True)
    parser.add_argument('subtype', type=str, help='子类型', location='form', required=True)
    parser.add_argument('page', type=int, help='页码', location='form', required=True)

    @recommend.doc(parser=parser)
    def post(self):
        """
        推荐列表
        """
        return get_recommend(self.parser.parse_args())


@rss.route('/info')
class RssInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任务ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅任务详情
        """
        return get_userrss_task(self.parser.parse_args())


@rss.route('/delete')
class RssDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任务ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        删除自定义订阅任务
        """
        return delete_userrss_task(self.parser.parse_args())


@rss.route('/update')
class RssUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任务ID', location='form')
    parser.add_argument('name', type=str, help='任务名称', location='form', required=True)
    parser.add_argument('address', type=str, help='RSS地址', location='form', required=True)
    parser.add_argument('parser', type=int, help='解析器ID', location='form', required=True)
    parser.add_argument('interval', type=int, help='刷新间隔（分钟）', location='form', required=True)
    parser.add_argument('uses', type=str, help='动作', location='form', required=True)
    parser.add_argument('state', type=str, help='状态（Y/N）', location='form', required=True)
    parser.add_argument('include', type=str, help='包含', location='form')
    parser.add_argument('exclude', type=str, help='排除', location='form')
    parser.add_argument('filterrule', type=int, help='过滤规则', location='form')
    parser.add_argument('note', type=str, help='备注', location='form')

    @rss.doc(parser=parser)
    def post(self):
        """
        新增/修改自定义订阅任务
        """
        return update_userrss_task(self.parser.parse_args())


@rss.route('/parser/info')
class RssParserInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        解析器详情
        """
        return get_rssparser(self.parser.parse_args())


@rss.route('/parser/delete')
class RssParserDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        删除解析器
        """
        return delete_rssparser(self.parser.parse_args())


@rss.route('/parser/update')
class RssParserUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（JSON/XML）', location='form', required=True)
    parser.add_argument('format', type=str, help='解析格式', location='form', required=True)
    parser.add_argument('params', type=str, help='附加参数', location='form')

    @rss.doc(parser=parser)
    def post(self):
        """
        新增/修改解析器
        """
        return update_rssparser(self.parser.parse_args())


@rss.route('/parser/list')
class RssParserList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有解析器
        """
        result = list_rss_parsers({})
        return {
            "code": 0,
            "success": True,
            "data": {
                "parsers": result.get("parsers")
            }
        }


@rss.route('/list')
class RssList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有自定义订阅任务
        """
        result = list_rss_tasks({})
        return {
            "code": 0,
            "success": False,
            "data": {
                "tasks": result.get("tasks"),
                "parsers": result.get("parsers")
            }
        }


@rss.route('/preview')
class RssPreview(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任务ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅预览
        """
        return list_rss_articles(self.parser.parse_args())


@rss.route('/name/test')
class RssNameTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('taskid', type=int, help='任务ID', location='form', required=True)
    parser.add_argument('title', type=str, help='名称', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅名称测试
        """
        return rss_article_test(self.parser.parse_args())


@rss.route('/item/history')
class RssItemHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任务ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅任务条目处理记录
        """
        return list_rss_history(self.parser.parse_args())


@rss.route('/item/set')
class RssItemSet(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='操作类型（set_finished/set_unfinish）', location='form', required=True)
    parser.add_argument('articles', type=list, help='条目（{title/enclosure}）', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅任务条目状态调整
        """
        return rss_articles_check(self.parser.parse_args())


@rss.route('/item/download')
class RssItemDownload(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('taskid', type=int, help='任务ID', location='form', required=True)
    parser.add_argument('articles', type=list, help='条目（{title/enclosure}）', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定义订阅任务条目下载
        """
        return rss_articles_download(self.parser.parse_args())


@media.route('/search')
class MediaSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('keyword', type=str, help='关键字', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        搜索TMDB/豆瓣词条
        """
        return search_media_infos(self.parser.parse_args())


@media.route('/cache/update')
class MediaCacheUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('key', type=str, help='缓存Key值', location='form', required=True)
    parser.add_argument('title', type=str, help='标题', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        修改TMDB缓存标题
        """
        args = self.parser.parse_args()
        from web.cache import cache
        cachekey = args.get("key")
        title = args.get("title")
        if not cachekey or not title:
            return Failed()
        try:
            cache.set(cachekey, title)
            return {"code": 0, "success": True}
        except Exception:
            return Failed()


@media.route('/cache/delete')
class MediaCacheDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cache_key', type=str, help='缓存Key值', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        删除TMDB缓存
        """
        args = self.parser.parse_args()
        from web.cache import cache
        cachekey = args.get("cache_key")
        if not cachekey:
            return Failed()
        try:
            cache.delete(cachekey)
            return {"code": 0, "success": True}
        except Exception:
            return Failed()


@media.route('/cache/clear')
class MediaCacheClear(ClientResource):

    @staticmethod
    def post():
        """
        清空TMDB缓存
        """
        from web.cache import cache
        try:
            cache.clear()
            return {"code": 0, "success": True}
        except Exception:
            return Failed()


@media.route('/tv/seasons')
class MediaTvSeasons(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查询电视剧季列表
        """
        return get_tvseason_list(self.parser.parse_args())


@media.route('/category/list')
class MediaCategoryList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（电影/电视剧/动漫）', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查询二级分类配置
        """
        return get_categories(self.parser.parse_args())


@media.route('/info')
class MediaInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('id', type=str, help='TMDBID/DB:豆瓣ID', location='form')
    parser.add_argument('title', type=str, help='标题', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('rssid', type=str, help='订阅ID', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        识别媒体信息
        """
        return media_info(self.parser.parse_args())


@media.route('/detail')
class MediaDetail(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID/DB:豆瓣ID', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        查询TMDB媒体详情
        """
        return media_detail(self.parser.parse_args())


@media.route('/similar')
class MediaSimilar(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        根据TMDBID查询类似媒体
        """
        return media_similar(self.parser.parse_args())


@media.route('/recommendations')
class MediaRecommendations(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        根据TMDBID查询推荐媒体
        """
        return media_recommendations(self.parser.parse_args())


@media.route('/person')
class MediaPersonList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('personid', type=str, help='演员ID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        查询TMDB演员参演作品
        """
        return person_medias(self.parser.parse_args())


@media.route('/subtitle/download')
class MediaSubtitleDownload(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('path', type=str, help='文件路径（含文件名）', location='form', required=True)
    parser.add_argument('name', type=str, help='名称（用于识别）', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        下载单个文件字幕
        """
        return download_subtitle(self.parser.parse_args())


@brushtask.route('/update')
class BrushTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('brushtask_id', type=str, help='刷流任务ID', location='form')
    parser.add_argument('brushtask_name', type=str, help='任务名称', location='form', required=True)
    parser.add_argument('brushtask_site', type=int, help='站点', location='form', required=True)
    parser.add_argument('brushtask_interval', type=int, help='刷新间隔(分钟)', location='form', required=True)
    parser.add_argument('brushtask_downloader', type=int, help='下载器', location='form', required=True)
    parser.add_argument('brushtask_totalsize', type=int, help='保种体积(GB)', location='form', required=True)
    parser.add_argument('brushtask_savepath', type=str, help='保存目录', location='form')
    parser.add_argument('brushtask_label', type=str, help='标签', location='form')
    parser.add_argument('brushtask_rssurl', type=str, help='RSS地址', location='form')
    parser.add_argument('brushtask_state', type=str, help='状态（Y/N）', location='form', required=True)
    parser.add_argument('brushtask_transfer', type=str, help='转移到媒体库（Y/N）', location='form')
    parser.add_argument('brushtask_sendmessage', type=str, help='消息推送（Y/N）', location='form')
    parser.add_argument('brushtask_free', type=str, help='促销（FREE/2XFREE）', location='form')
    parser.add_argument('brushtask_hr', type=str, help='Hit&Run（HR）', location='form')
    parser.add_argument('brushtask_torrent_size', type=int, help='种子大小(GB)', location='form')
    parser.add_argument('brushtask_include', type=str, help='包含', location='form')
    parser.add_argument('brushtask_exclude', type=str, help='排除', location='form')
    parser.add_argument('brushtask_dlcount', type=int, help='同时下载任务数', location='form')
    parser.add_argument('brushtask_peercount', type=int, help='做种人数限制', location='form')
    parser.add_argument('brushtask_seedtime', type=float, help='做种时间(小时)', location='form')
    parser.add_argument('brushtask_hr_seedtime', type=float, help='H&R 做种时间(小时)', location='form')
    parser.add_argument('brushtask_seedratio', type=float, help='分享率', location='form')
    parser.add_argument('brushtask_seedsize', type=int, help='上传量(GB)', location='form')
    parser.add_argument('brushtask_dltime', type=float, help='下载耗时(小时)', location='form')
    parser.add_argument('brushtask_avg_upspeed', type=int, help='平均上传速度(KB/S)', location='form')
    parser.add_argument('brushtask_iatime', type=float, help='未活动时间(小时)', location='form')
    parser.add_argument('brushtask_pubdate', type=int, help='发布时间（小时）', location='form')
    parser.add_argument('brushtask_upspeed', type=int, help='上传限速（KB/S）', location='form')
    parser.add_argument('brushtask_downspeed', type=int, help='下载限速（KB/S）', location='form')

    @brushtask.doc(parser=parser)
    def post(self):
        """
        新增/修改刷流任务
        """
        return add_brushtask(self.parser.parse_args())


@brushtask.route('/delete')
class BrushTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        删除刷流任务
        """
        return del_brushtask(self.parser.parse_args())


@brushtask.route('/info')
class BrushTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流任务详情
        """
        return brushtask_detail(self.parser.parse_args())


@brushtask.route('/list')
class BrushTaskList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有刷流任务
        """
        result = list_brushtasks({})
        return {
            "code": 0,
            "success": True,
            "data": {
                "tasks": result.get("tasks")
            }
        }


@brushtask.route('/torrents')
class BrushTaskTorrents(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        查询刷流任务种子明细
        """
        return list_brushtask_torrents(self.parser.parse_args())


@brushtask.route('/run')
class BrushTaskRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        立即运行刷流任务
        """
        return run_brushtask(self.parser.parse_args())


@filterrule.route('/list')
class FilterRuleList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有过滤规则
        """
        return get_filterrules({})


@filterrule.route('/group/add')
class FilterRuleGroupAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('default', type=str, help='默认（Y/N）', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        新增规则组
        """
        return add_filtergroup(self.parser.parse_args())


@filterrule.route('/group/restore')
class FilterRuleGroupRestore(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('groupids', type=list, help='规则组ID', location='form', required=True)
    parser.add_argument('init_rulegroups', type=list, help='规则组脚本', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        恢复默认规则组
        """
        return restore_filtergroup(self.parser.parse_args())


@filterrule.route('/group/default')
class FilterRuleGroupDefault(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='规则组ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        设置默认规则组
        """
        return set_default_filtergroup(self.parser.parse_args())


@filterrule.route('/group/delete')
class FilterRuleGroupDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='规则组ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        删除规则组
        """
        return del_filtergroup(self.parser.parse_args())


@filterrule.route('/rule/update')
class FilterRuleUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rule_id', type=int, help='规则ID', location='form')
    parser.add_argument('group_id', type=int, help='规则组ID', location='form', required=True)
    parser.add_argument('rule_name', type=str, help='规则名称', location='form', required=True)
    parser.add_argument('rule_pri', type=str, help='优先级', location='form', required=True)
    parser.add_argument('rule_include', type=str, help='包含', location='form')
    parser.add_argument('rule_exclude', type=str, help='排除', location='form')
    parser.add_argument('rule_sizelimit', type=str, help='大小限制', location='form')
    parser.add_argument('rule_free', type=str, help='促销（FREE/2XFREE）', location='form')

    @filterrule.doc(parser=parser)
    def post(self):
        """
        新增/修改规则
        """
        return add_filterrule(self.parser.parse_args())


@filterrule.route('/rule/delete')
class FilterRuleDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='规则ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        删除规则
        """
        return del_filterrule(self.parser.parse_args())


@filterrule.route('/rule/info')
class FilterRuleInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ruleid', type=int, help='规则ID', location='form', required=True)
    parser.add_argument('groupid', type=int, help='规则组ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        规则详情
        """
        return filterrule_detail(self.parser.parse_args())


@filterrule.route('/rule/share')
class FilterRuleShare(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='规则组ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        分享规则组
        """
        return share_filtergroup(self.parser.parse_args())


@filterrule.route('/rule/import')
class FilterRuleImport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('content', type=str, help='规则内容', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        导入规则组
        """
        return import_filtergroup(self.parser.parse_args())


@words.route('/group/add')
class WordsGroupAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tmdb_id', type=str, help='TMDBID', location='form', required=True)
    parser.add_argument('tmdb_type', type=str, help='类型（movie/tv）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        新增识别词组
        """
        return add_custom_word_group(self.parser.parse_args())


@words.route('/group/delete')
class WordsGroupDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('gid', type=int, help='识别词组ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        删除识别词组
        """
        return delete_custom_word_group(self.parser.parse_args())


@words.route('/item/update')
class WordItemUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='识别词ID', location='form', required=True)
    parser.add_argument('gid', type=int, help='识别词组ID', location='form', required=True)
    parser.add_argument('group_type', type=str, help='媒体类型（1-电影/2-电视剧）', location='form', required=True)
    parser.add_argument('new_replaced', type=str, help='被替换词', location='form')
    parser.add_argument('new_replace', type=str, help='替换词', location='form')
    parser.add_argument('new_front', type=str, help='前定位词', location='form')
    parser.add_argument('new_back', type=str, help='后定位词', location='form')
    parser.add_argument('new_offset', type=str, help='偏移集数', location='form')
    parser.add_argument('new_help', type=str, help='备注', location='form')
    parser.add_argument('type', type=str, help='识别词类型（1-屏蔽/2-替换/3-替换+集偏移/4-集偏移）', location='form',
                        required=True)
    parser.add_argument('season', type=str, help='季', location='form')
    parser.add_argument('enabled', type=str, help='状态（1-启用/0-停用）', location='form', required=True)
    parser.add_argument('regex', type=str, help='正则表达式（1-使用/0-不使用）', location='form')

    @words.doc(parser=parser)
    def post(self):
        """
        新增/修改识别词
        """
        return add_or_edit_custom_word(self.parser.parse_args())


@words.route('/item/info')
class WordItemInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('wid', type=int, help='识别词ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        识别词详情
        """
        return get_custom_word(self.parser.parse_args())


@words.route('/item/delete')
class WordItemDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='识别词ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        删除识别词
        """
        return delete_custom_words(self.parser.parse_args())


@words.route('/item/status')
class WordItemStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ids_info', type=list, help='识别词IDS', location='form', required=True)
    parser.add_argument('flag', type=int, help='状态（1/0）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        设置识别词状态
        """
        return check_custom_words(self.parser.parse_args())


@words.route('/item/export')
class WordItemExport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('note', type=str, help='备注', location='form', required=True)
    parser.add_argument('ids_info', type=str, help='识别词IDS（@_）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        导出识别词
        """
        return export_custom_words(self.parser.parse_args())


@words.route('/item/analyse')
class WordItemAnalyse(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('import_code', type=str, help='识别词代码', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        分析识别词
        """
        return analyse_import_custom_words_code(self.parser.parse_args())


@words.route('/item/import')
class WordItemImport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('import_code', type=str, help='识别词代码', location='form', required=True)
    parser.add_argument('ids_info', type=list, help='识别词IDS', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        导入识别词
        """
        return import_custom_words(self.parser.parse_args())


@words.route('/list')
class WordList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有自定义识别词
        """
        return get_customwords({})


@sync.route('/directory/update')
class SyncDirectoryUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目录ID', location='form')
    parser.add_argument('from', type=str, help='源目录', location='form', required=True)
    parser.add_argument('to', type=str, help='目的目录', location='form')
    parser.add_argument('unknown', type=str, help='未知目录', location='form')
    parser.add_argument('syncmod', type=str, help='同步模式', location='form')
    parser.add_argument('compatibility', type=str, help='兼容模式', location='form')
    parser.add_argument('rename', type=str, help='重命名', location='form')
    parser.add_argument('enabled', type=str, help='开启', location='form')

    @sync.doc(parser=parser)
    def post(self):
        """
        新增/修改同步目录
        """
        return add_or_edit_sync_path(self.parser.parse_args())


@sync.route('/directory/info')
class SyncDirectoryInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目录ID', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        同步目录详情
        """
        return get_sync_path(self.parser.parse_args())


@sync.route('/directory/delete')
class SyncDirectoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目录ID', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        删除同步目录
        """
        return delete_sync_path(self.parser.parse_args())


@sync.route('/directory/status')
class SyncDirectoryStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目录ID', location='form', required=True)
    parser.add_argument('flag', type=str, help='操作（rename/enable）', location='form', required=True)
    parser.add_argument('checked', type=int, help='状态（0-否/1-是）', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        设置同步目录状态
        """
        return check_sync_path(self.parser.parse_args())


@sync.route('/directory/list')
class SyncDirectoryList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有同步目录
        """
        return get_sync_path({})


@sync.route('/directory/run')
class SyncDirectoryRun(ApiResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目录ID', location='args', required=True)

    @sync.doc(parser=parser)
    def get(self):
        """
        立即运行单个目录同步服务（密钥认证）
        """
        return run_directory_sync(self.parser.parse_args())


@sync.route('/run')
class SyncRun(ApiResource):

    @staticmethod
    def get():
        """
        立即运行所有目录同步服务（密钥认证）
        """
        return sch({"item": "sync"})


@message.route('/client/update')
class MessageClientUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（wechat/telegram/serverchan/bark/pushplus/iyuu/slack/gotify）',
                        location='form', required=True)
    parser.add_argument('config', type=str, help='配置项（JSON）', location='form', required=True)
    parser.add_argument('switchs', type=list, help='开关', location='form', required=True)
    parser.add_argument('interactive', type=int, help='是否开启交互（0/1）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='是否启用（0/1）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        新增/修改通知消息服务渠道
        """
        return update_message_client(self.parser.parse_args())


@message.route('/client/delete')
class MessageClientDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        删除通知消息服务渠道
        """
        return delete_message_client(self.parser.parse_args())


@message.route('/client/status')
class MessageClientStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='操作类型（interactive/enable）', location='form', required=True)
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        设置通知消息服务渠道状态
        """
        return check_message_client(self.parser.parse_args())


@message.route('/client/info')
class MessageClientInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        查询通知消息服务渠道设置
        """
        return get_message_client(self.parser.parse_args())


@message.route('/client/test')
class MessageClientTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（wechat/telegram/serverchan/bark/pushplus/iyuu/slack/gotify）',
                        location='form', required=True)
    parser.add_argument('config', type=str, help='配置（JSON）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        测试通知消息服务配置正确性
        """
        return test_message_client(self.parser.parse_args())


@torrentremover.route('/task/info')
class TorrentRemoverTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        查询自动删种任务详情
        """
        return get_torrent_remove_task(self.parser.parse_args())


@torrentremover.route('/task/list')
class TorrentRemoverTaskList(ClientResource):
    @staticmethod
    @torrentremover.doc()
    def post():
        """
        查询所有自动删种任务
        """
        return get_torrent_remove_task({})


@torrentremover.route('/task/delete')
class TorrentRemoverTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        删除自动删种任务
        """
        return delete_torrent_remove_task(self.parser.parse_args())


@torrentremover.route('/task/update')
class TorrentRemoverTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('action', type=int, help='动作(1-暂停/2-删除种子/3-删除种子及文件)', location='form',
                        required=True)
    parser.add_argument('interval', type=int, help='运行间隔（分钟）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='状态（0-停用/1-启用）', location='form', required=True)
    parser.add_argument('samedata', type=int, help='处理辅种（0-否/1-是）', location='form', required=True)
    parser.add_argument('onlynastool', type=int, help='只管理NAStool添加的下载（0-否/1-是）', location='form',
                        required=True)
    parser.add_argument('ratio', type=float, help='分享率', location='form')
    parser.add_argument('seeding_time', type=int, help='做种时间（小时）', location='form')
    parser.add_argument('upload_avs', type=int, help='平均上传速度（KB/S）', location='form')
    parser.add_argument('size', type=str, help='种子大小（GB）', location='form')
    parser.add_argument('savepath_key', type=str, help='保存路径关键词', location='form')
    parser.add_argument('tracker_key', type=str, help='tracker关键词', location='form')
    parser.add_argument('downloader', type=str, help='下载器（Qb/Tr）', location='form')
    parser.add_argument('qb_state', type=str, help='Qb种子状态（多个用;分隔）', location='form')
    parser.add_argument('qb_category', type=str, help='Qb分类（多个用;分隔）', location='form')
    parser.add_argument('tr_state', type=str, help='Tr种子状态（多个用;分隔）', location='form')
    parser.add_argument('tr_error_key', type=str, help='Tr错误信息关键词', location='form')

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        新增/修改自动删种任务
        """
        return update_torrent_remove_task(self.parser.parse_args())


@plugin.route('/install')
class PluginInstall(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='插件ID', location='form', required=True)

    @plugin.doc(parser=parser)
    def post(self):
        """
        安装插件
        """
        return install_plugin(self.parser.parse_args())


@plugin.route('/uninstall')
class PluginUninstall(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='插件ID', location='form', required=True)

    @plugin.doc(parser=parser)
    def post(self):
        """
        卸载插件
        """
        return uninstall_plugin(self.parser.parse_args())


@plugin.route('/apps')
class PluginApps(ClientResource):
    @staticmethod
    @plugin.doc()
    def post():
        """
        获取插件市场所有插件
        """
        return get_plugin_apps({})


@plugin.route('/list')
class PluginList(ClientResource):
    @staticmethod
    @plugin.doc()
    def post():
        """
        获取已安装插件
        """
        return get_plugins_conf({})


@plugin.route('/status')
class PluginStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='插件ID', location='form', required=True)

    @plugin.doc(parser=parser)
    def post(self):
        """
        获取插件运行状态
        """
        return get_plugin_state(self.parser.parse_args())
