"""
Config Repository
Handles configuration related database operations.
Includes: Message Client, Torrent Remove Task, Downloader, User RSS, Filter Rules
"""

import json
import time

from sqlalchemy import Integer, cast

from app.db import DbPersist
from app.db.models import (
    CONFIGFILTERGROUP,
    CONFIGFILTERRULES,
    CONFIGMEDIA,
    CONFIGRSSPARSER,
    CONFIGUSERRSS,
    DOWNLOADER,
    MEDIASERVER,
    MESSAGECLIENT,
    TORRENTREMOVETASK,
    USERRSSTASKHISTORY,
)
from app.db.repositories.base_repository import BaseRepository


class ConfigRepository(BaseRepository):
    """
    配置仓储
    处理消息客户端、自动删种策略、下载器、自定义RSS、过滤规则的数据库操作
    """

    # ==================== Message Client ====================

    @DbPersist(BaseRepository._db)
    def delete_message_client(self, cid: int | None) -> None:
        """
        删除消息服务器

        Args:
            cid: 客户端ID
        """
        if not cid:
            return
        self._db.query(MESSAGECLIENT).filter(int(cid) == MESSAGECLIENT.ID).delete()

    def get_message_client(self, cid: int | None = None) -> list[MESSAGECLIENT]:
        if cid:
            return self._db.query(MESSAGECLIENT).filter(int(cid) == MESSAGECLIENT.ID).all()
        return self._db.query(MESSAGECLIENT).all()

    @DbPersist(BaseRepository._db)
    def insert_message_client(self, name: str, ctype: str, config: str, switchs: list, interactive: int, enabled: int, note: str = "", templates: str | None = None) -> int:
        client = MESSAGECLIENT(
            NAME=name,
            TYPE=ctype,
            CONFIG=config,
            SWITCHS=json.dumps(switchs),
            INTERACTIVE=int(interactive),
            ENABLED=int(enabled),
            NOTE=note,
            TEMPLATES=json.dumps(templates) if templates else None,
        )
        self._db.insert(client)
        self._db.flush()
        return client.ID

    @DbPersist(BaseRepository._db)
    def check_message_client(self, cid: int | None = None, interactive: int | None = None, enabled: int | None = None, ctype: str | None = None) -> None:
        """
        设置消息客户端状态

        Args:
            cid: 客户端ID
            interactive: 是否交互
            enabled: 是否启用
            ctype: 类型
        """
        if cid and interactive is not None:
            self._db.query(MESSAGECLIENT).filter(int(cid) == MESSAGECLIENT.ID).update({"INTERACTIVE": int(interactive)})
        elif cid and enabled is not None:
            self._db.query(MESSAGECLIENT).filter(int(cid) == MESSAGECLIENT.ID).update({"ENABLED": int(enabled)})
        elif not cid and int(interactive or 0) == 0 and ctype:
            self._db.query(MESSAGECLIENT).filter(MESSAGECLIENT.INTERACTIVE == 1, ctype == MESSAGECLIENT.TYPE).update(
                {"INTERACTIVE": 0}
            )

    # ==================== Torrent Remove Task ====================

    @DbPersist(BaseRepository._db)
    def delete_torrent_remove_task(self, tid: int | None) -> None:
        """
        删除自动删种策略

        Args:
            tid: 任务ID
        """
        if not tid:
            return
        self._db.query(TORRENTREMOVETASK).filter(int(tid) == TORRENTREMOVETASK.ID).delete()

    def get_torrent_remove_tasks(self, tid: int | None = None) -> list[TORRENTREMOVETASK]:
        """
        查询自动删种策略

        Args:
            tid: 任务ID

        Returns:
            删种策略列表
        """
        if tid:
            return self._db.query(TORRENTREMOVETASK).filter(int(tid) == TORRENTREMOVETASK.ID).all()
        return self._db.query(TORRENTREMOVETASK).order_by(TORRENTREMOVETASK.NAME).all()

    @DbPersist(BaseRepository._db)
    def insert_torrent_remove_task(
        self, name: str, action: int, interval: int, enabled: int, samedata: int, onlynastool: int, downloader: str, config: dict, note: str | None = None
    ) -> None:
        """
        设置自动删种策略

        Args:
            name: 名称
            action: 动作
            interval: 间隔
            enabled: 是否启用
            samedata: 相同数据处理
            onlynastool: 仅NAStool
            downloader: 下载器
            config: 配置
            note: 备注
        """
        self._db.insert(
            TORRENTREMOVETASK(
                NAME=name,
                ACTION=int(action),
                INTERVAL=int(interval),
                ENABLED=int(enabled),
                SAMEDATA=int(samedata),
                ONLYNASTOOL=int(onlynastool),
                DOWNLOADER=downloader,
                CONFIG=json.dumps(config),
                NOTE=note,
            )
        )

    # ==================== Downloader ====================

    @DbPersist(BaseRepository._db)
    def update_downloader(
        self, did: int | None, name: str, enabled: int, dtype: str, transfer: int, only_nastool: int, match_path: int, rmt_mode: str, config: str, download_dir: str
    ) -> None:
        """
        更新下载器

        Args:
            did: 下载器ID
            name: 名称
            enabled: 是否启用
            dtype: 类型
            transfer: 是否转移
            only_nastool: 仅NAStool
            match_path: 匹配路径
            rmt_mode: 转移模式
            config: 配置
            download_dir: 下载目录
        """
        if did:
            self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).update(
                {
                    "NAME": name,
                    "ENABLED": int(enabled),
                    "TYPE": dtype,
                    "TRANSFER": int(transfer),
                    "ONLY_NASTOOL": int(only_nastool),
                    "MATCH_PATH": int(match_path),
                    "RMT_MODE": rmt_mode,
                    "CONFIG": config,
                    "DOWNLOAD_DIR": download_dir,
                }
            )
        else:
            self._db.insert(
                DOWNLOADER(
                    NAME=name,
                    ENABLED=int(enabled),
                    TYPE=dtype,
                    TRANSFER=int(transfer),
                    ONLY_NASTOOL=int(only_nastool),
                    MATCH_PATH=int(match_path),
                    RMT_MODE=rmt_mode,
                    CONFIG=config,
                    DOWNLOAD_DIR=download_dir,
                )
            )

    @DbPersist(BaseRepository._db)
    def delete_downloader(self, did: int | None) -> None:
        """
        删除下载器

        Args:
            did: 下载器ID
        """
        if not did:
            return
        self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).delete()

    @DbPersist(BaseRepository._db)
    def check_downloader(self, did: int | None = None, transfer: int | None = None, only_nastool: int | None = None, enabled: int | None = None, match_path: int | None = None) -> None:
        """
        设置下载器状态

        Args:
            did: 下载器ID
            transfer: 是否转移
            only_nastool: 仅NAStool
            enabled: 是否启用
            match_path: 匹配路径
        """
        if not did:
            return
        if transfer is not None:
            self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).update({"TRANSFER": int(transfer)})
        elif only_nastool is not None:
            self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).update({"ONLY_NASTOOL": int(only_nastool)})
        elif match_path is not None:
            self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).update({"MATCH_PATH": int(match_path)})
        elif enabled is not None:
            self._db.query(DOWNLOADER).filter(int(did) == DOWNLOADER.ID).update({"ENABLED": int(enabled)})

    def get_downloaders(self) -> list[DOWNLOADER]:
        """
        查询下载器

        Returns:
            下载器列表
        """
        return self._db.query(DOWNLOADER).all()

    # ==================== User RSS ====================

    def get_userrss_tasks(self, tid: int | None = None) -> list[CONFIGUSERRSS]:
        """
        查询自定义RSS任务

        Args:
            tid: 任务ID

        Returns:
            任务列表
        """
        if tid:
            return self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).all()
        else:
            return self._db.query(CONFIGUSERRSS).order_by(CONFIGUSERRSS.STATE.desc()).all()

    @DbPersist(BaseRepository._db)
    def delete_userrss_task(self, tid: int | None) -> None:
        """
        删除自定义RSS任务

        Args:
            tid: 任务ID
        """
        if not tid:
            return
        self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).delete()

    @DbPersist(BaseRepository._db)
    def update_userrss_task_info(self, tid: int | None, count: int) -> None:
        """
        更新自定义RSS任务处理计数

        Args:
            tid: 任务ID
            count: 处理数量
        """
        if not tid:
            return
        self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).update(
            {
                "PROCESS_COUNT": CONFIGUSERRSS.PROCESS_COUNT + count,
                "UPDATE_TIME": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            }
        )

    @DbPersist(BaseRepository._db)
    def update_userrss_task(self, item: dict) -> None:
        """
        更新或插入自定义RSS任务

        Args:
            item: 任务信息字典
        """
        if item.get("id") and self.get_userrss_tasks(item.get("id")):
            self._db.query(CONFIGUSERRSS).filter(int(item.get("id") or 0) == CONFIGUSERRSS.ID).update(
                {
                    "NAME": item.get("name"),
                    "ADDRESS": json.dumps(item.get("address")),
                    "PARSER": json.dumps(item.get("parser")),
                    "INTERVAL": item.get("interval"),
                    "USES": item.get("uses"),
                    "INCLUDE": item.get("include"),
                    "EXCLUDE": item.get("exclude"),
                    "FILTER": item.get("filter_rule"),
                    "UPDATE_TIME": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                    "STATE": item.get("state"),
                    "SAVE_PATH": item.get("save_path"),
                    "DOWNLOAD_SETTING": item.get("download_setting"),
                    "RECOGNIZATION": item.get("recognization"),
                    "OVER_EDITION": int(item.get("over_edition") or 0) if str(item.get("over_edition") or "").isdigit() else 0,
                    "SITES": json.dumps(item.get("sites")),
                    "FILTER_ARGS": json.dumps(item.get("filter_args")),
                    "NOTE": json.dumps(item.get("note")),
                }
            )
        else:
            self._db.insert(
                CONFIGUSERRSS(
                    NAME=item.get("name"),
                    ADDRESS=json.dumps(item.get("address")),
                    PARSER=json.dumps(item.get("parser")),
                    INTERVAL=item.get("interval"),
                    USES=item.get("uses"),
                    INCLUDE=item.get("include"),
                    EXCLUDE=item.get("exclude"),
                    FILTER=item.get("filter_rule"),
                    UPDATE_TIME=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                    STATE=item.get("state"),
                    SAVE_PATH=item.get("save_path"),
                    DOWNLOAD_SETTING=item.get("download_setting"),
                    RECOGNIZATION=item.get("recognization"),
                    OVER_EDITION=item.get("over_edition"),
                    SITES=json.dumps(item.get("sites")),
                    FILTER_ARGS=json.dumps(item.get("filter_args")),
                    NOTE=json.dumps(item.get("note")),
                    PROCESS_COUNT="0",
                )
            )

    @DbPersist(BaseRepository._db)
    def check_userrss_task(self, tid: int | None = None, state: str | None = None) -> None:
        """
        设置自定义RSS任务状态

        Args:
            tid: 任务ID
            state: 状态
        """
        if state is None:
            return
        if tid:
            self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).update({"STATE": state})
        else:
            self._db.query(CONFIGUSERRSS).update({"STATE": state})

    @DbPersist(BaseRepository._db)
    def insert_userrss_mediainfos(self, tid: int | None = None, mediainfo: object | None = None) -> None:
        """
        插入自定义RSS媒体信息

        Args:
            tid: 任务ID
            mediainfo: 媒体信息
        """
        if not tid or not mediainfo:
            return
        taskinfo = self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).all()
        if not taskinfo:
            return

        mediainfos = json.loads(taskinfo[0].MEDIAINFOS) if taskinfo[0].MEDIAINFOS else []
        tmdbid = str(mediainfo.tmdb_id)
        season = int(mediainfo.get_season_seq())

        for media in mediainfos:
            if media.get("id") == tmdbid and media.get("season") == season:
                return

        mediainfos.append({"id": tmdbid, "rssid": "", "season": season, "name": mediainfo.title})

        self._db.query(CONFIGUSERRSS).filter(int(tid) == CONFIGUSERRSS.ID).update(
            {"MEDIAINFOS": json.dumps(mediainfos)}
        )

    @DbPersist(BaseRepository._db)
    def insert_userrss_task_history(self, task_id: int, title: str, downloader: str) -> None:
        """
        增加自定义RSS订阅任务的下载记录

        Args:
            task_id: 任务ID
            title: 标题
            downloader: 下载器
        """
        self._db.insert(
            USERRSSTASKHISTORY(
                TASK_ID=task_id,
                TITLE=title,
                DOWNLOADER=downloader,
                DATE=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            )
        )

    def get_userrss_task_history(self, task_id: int) -> list[USERRSSTASKHISTORY]:
        """
        查询自定义RSS订阅任务的下载记录

        Args:
            task_id: 任务ID

        Returns:
            历史记录列表
        """
        if not task_id:
            return []
        return (
            self._db.query(USERRSSTASKHISTORY)
            .filter(task_id == USERRSSTASKHISTORY.TASK_ID)
            .order_by(USERRSSTASKHISTORY.DATE.desc())
            .all()
        )

    # ==================== RSS Parser ====================

    def get_userrss_parser(self, pid: int | None = None) -> CONFIGRSSPARSER | None | list[CONFIGRSSPARSER]:
        """
        获取自定义RSS解析器

        Args:
            pid: 解析器ID

        Returns:
            解析器列表或单个解析器
        """
        if pid:
            return self._db.query(CONFIGRSSPARSER).filter(int(pid) == CONFIGRSSPARSER.ID).first()
        else:
            return self._db.query(CONFIGRSSPARSER).all()

    @DbPersist(BaseRepository._db)
    def delete_userrss_parser(self, pid: int | None) -> None:
        """
        删除自定义RSS解析器

        Args:
            pid: 解析器ID
        """
        if not pid:
            return
        self._db.query(CONFIGRSSPARSER).filter(int(pid) == CONFIGRSSPARSER.ID).delete()

    @DbPersist(BaseRepository._db)
    def update_userrss_parser(self, item: dict) -> None:
        """
        更新或插入自定义RSS解析器

        Args:
            item: 解析器信息字典
        """
        if not item:
            return
        if item.get("id") and self.get_userrss_parser(item.get("id")):
            self._db.query(CONFIGRSSPARSER).filter(int(item.get("id") or 0) == CONFIGRSSPARSER.ID).update(
                {
                    "NAME": item.get("name"),
                    "TYPE": item.get("type"),
                    "FORMAT": item.get("format"),
                    "PARAMS": item.get("params"),
                }
            )
        else:
            self._db.insert(
                CONFIGRSSPARSER(
                    NAME=item.get("name"), TYPE=item.get("type"), FORMAT=item.get("format"), PARAMS=item.get("params")
                )
            )

    # ==================== Filter Rules ====================

    def get_config_filter_group(self, gid: int | None = None) -> list[CONFIGFILTERGROUP]:
        """
        查询过滤规则组

        Args:
            gid: 组ID

        Returns:
            规则组列表
        """
        if gid:
            return self._db.query(CONFIGFILTERGROUP).filter(int(gid) == CONFIGFILTERGROUP.ID).all()
        return self._db.query(CONFIGFILTERGROUP).all()

    def get_config_filter_rule(self, groupid: int | None = None) -> list[CONFIGFILTERRULES]:
        """
        查询过滤规则

        Args:
            groupid: 组ID

        Returns:
            规则列表
        """
        if not groupid:
            return (
                self._db.query(CONFIGFILTERRULES)
                .order_by(CONFIGFILTERRULES.GROUP_ID, cast(CONFIGFILTERRULES.PRIORITY, Integer))
                .all()
            )
        else:
            return (
                self._db.query(CONFIGFILTERRULES)
                .filter(int(groupid) == CONFIGFILTERRULES.GROUP_ID)
                .order_by(CONFIGFILTERRULES.GROUP_ID, cast(CONFIGFILTERRULES.PRIORITY, Integer))
                .all()
            )

    @DbPersist(BaseRepository._db)
    def add_filter_group(self, name: str, default: str = "N") -> None:
        """
        新增规则组

        Args:
            name: 组名
            default: 是否默认
        """
        if default == "Y":
            self.set_default_filtergroup(0)
        group_id = self.get_filter_groupid_by_name(name)
        if group_id:
            self._db.query(CONFIGFILTERGROUP).filter(int(group_id) == CONFIGFILTERGROUP.ID).update(
                {"IS_DEFAULT": default}
            )
        else:
            self._db.insert(CONFIGFILTERGROUP(GROUP_NAME=name, IS_DEFAULT=default))

    def get_filter_groupid_by_name(self, name: str) -> int | str:
        """
        根据名称获取规则组ID

        Args:
            name: 组名

        Returns:
            组ID
        """
        ret = self._db.query(CONFIGFILTERGROUP.ID).filter(name == CONFIGFILTERGROUP.GROUP_NAME).first()
        if ret:
            return ret[0]
        else:
            return ""

    @DbPersist(BaseRepository._db)
    def set_default_filtergroup(self, groupid: int) -> None:
        """
        设置默认的规则组

        Args:
            groupid: 组ID
        """
        self._db.query(CONFIGFILTERGROUP).filter(int(groupid) == CONFIGFILTERGROUP.ID).update({"IS_DEFAULT": "Y"})
        self._db.query(CONFIGFILTERGROUP).filter(int(groupid) != CONFIGFILTERGROUP.ID).update({"IS_DEFAULT": "N"})

    @DbPersist(BaseRepository._db)
    def delete_filtergroup(self, groupid: int) -> None:
        """
        删除规则组

        Args:
            groupid: 组ID
        """
        self._db.query(CONFIGFILTERRULES).filter(groupid == CONFIGFILTERRULES.GROUP_ID).delete()
        self._db.query(CONFIGFILTERGROUP).filter(int(groupid) == CONFIGFILTERGROUP.ID).delete()

    @DbPersist(BaseRepository._db)
    def delete_filterrule(self, ruleid: int) -> None:
        """
        删除规则

        Args:
            ruleid: 规则ID
        """
        self._db.query(CONFIGFILTERRULES).filter(int(ruleid) == CONFIGFILTERRULES.ID).delete()

    @DbPersist(BaseRepository._db)
    def insert_filter_rule(self, item: dict, ruleid: int | None = None) -> None:
        """
        新增或更新规则

        Args:
            item: 规则信息字典
            ruleid: 规则ID（可选）
        """
        if ruleid:
            self._db.query(CONFIGFILTERRULES).filter(int(ruleid) == CONFIGFILTERRULES.ID).update(
                {
                    "ROLE_NAME": item.get("name"),
                    "PRIORITY": item.get("pri"),
                    "INCLUDE": item.get("include"),
                    "EXCLUDE": item.get("exclude"),
                    "SIZE_LIMIT": item.get("size"),
                    "NOTE": item.get("free"),
                }
            )
        else:
            self._db.insert(
                CONFIGFILTERRULES(
                    GROUP_ID=item.get("group"),
                    ROLE_NAME=item.get("name"),
                    PRIORITY=item.get("pri"),
                    INCLUDE=item.get("include"),
                    EXCLUDE=item.get("exclude"),
                    SIZE_LIMIT=item.get("size"),
                    NOTE=item.get("free"),
                )
            )

    # ==================== Media Server ====================

    def get_media_servers(self, sid: int | None = None) -> list[MEDIASERVER]:
        """
        查询媒体服务器配置

        Args:
            sid: 服务器ID

        Returns:
            媒体服务器配置列表
        """
        if sid:
            return self._db.query(MEDIASERVER).filter(int(sid) == MEDIASERVER.ID).all()
        return self._db.query(MEDIASERVER).all()

    def get_media_server_by_name(self, name: str) -> MEDIASERVER | None:
        """
        根据名称查询媒体服务器配置

        Args:
            name: 服务器名称

        Returns:
            媒体服务器配置
        """
        if not name:
            return None
        return self._db.query(MEDIASERVER).filter(name == MEDIASERVER.NAME).first()

    @DbPersist(BaseRepository._db)
    def update_media_server(self, sid: int | None, name: str, enabled: int, config: str, is_default: int = 0, note: str | None = None) -> None:
        """
        更新或插入媒体服务器配置

        Args:
            sid: 服务器ID
            name: 名称
            enabled: 是否启用
            config: 配置(JSON字符串)
            is_default: 是否默认
            note: 备注
        """
        if sid:
            item = self.get_media_servers(sid)
            if item:
                self._db.query(MEDIASERVER).filter(int(sid) == MEDIASERVER.ID).update(
                    {
                        "NAME": name,
                        "ENABLED": int(enabled),
                        "CONFIG": config,
                        "IS_DEFAULT": int(is_default),
                        "NOTE": note,
                    }
                )
                return
        self._db.insert(
            MEDIASERVER(NAME=name, ENABLED=int(enabled), CONFIG=config, IS_DEFAULT=int(is_default), NOTE=note)
        )

    @DbPersist(BaseRepository._db)
    def delete_media_server(self, sid: int | None) -> None:
        """
        删除媒体服务器配置

        Args:
            sid: 服务器ID
        """
        if not sid:
            return
        self._db.query(MEDIASERVER).filter(int(sid) == MEDIASERVER.ID).delete()

    @DbPersist(BaseRepository._db)
    def set_default_media_server(self, name: str) -> None:
        """
        设置默认媒体服务器，仅更新 IS_DEFAULT 标记

        Args:
            name: 服务器名称
        """
        self._db.query(MEDIASERVER).update({"IS_DEFAULT": 0})
        if name:
            self._db.query(MEDIASERVER).filter(name == MEDIASERVER.NAME).update({"IS_DEFAULT": 1})

    def get_default_media_server(self) -> MEDIASERVER | None:
        """
        获取默认媒体服务器

        Returns:
            默认媒体服务器配置
        """
        return self._db.query(MEDIASERVER).filter(MEDIASERVER.IS_DEFAULT == 1).first()

    # ==================== SQL Operations ====================

    @DbPersist(BaseRepository._db)
    def execute(self, sql: str) -> object:
        """
        执行SQL语句

        Args:
            sql: SQL语句

        Returns:
            执行结果
        """
        return self._db.execute(sql)

    @DbPersist(BaseRepository._db)
    def drop_table(self, table_name: str) -> object:
        """
        删除表

        Args:
            table_name: 表名

        Returns:
            执行结果
        """
        return self._db.execute(f"""DROP TABLE IF EXISTS {table_name}""")

    # ==================== Media Config ====================

    def get_media_config(self) -> CONFIGMEDIA | None:
        """获取媒体库路径配置"""
        return self._db.query(CONFIGMEDIA).first()

    def _update_media_config_col(self, col_name: str, value: str) -> None:
        """更新 CONFIG_MEDIA 表的单个列（由 MediaConfigRepositoryAdapter 调用）"""
        existing = self._db.query(CONFIGMEDIA).first()
        if existing:
            setattr(existing, col_name, value)
            self._db.commit()
        else:
            config = CONFIGMEDIA(**{col_name: value})
            self._db.insert(config)
            self._db.commit()

    @DbPersist(BaseRepository._db)
    def set_media_config(self, movie_path: str, tv_path: str, anime_path: str, unknown_path: str) -> None:
        """设置媒体库路径配置（单条记录）"""
        existing = self._db.query(CONFIGMEDIA).first()
        if existing:
            existing.MOVIE_PATH = movie_path
            existing.TV_PATH = tv_path
            existing.ANIME_PATH = anime_path
            existing.UNKNOWN_PATH = unknown_path
        else:
            config = CONFIGMEDIA(
                MOVIE_PATH=movie_path,
                TV_PATH=tv_path,
                ANIME_PATH=anime_path,
                UNKNOWN_PATH=unknown_path,
            )
            self._db.insert(config)
