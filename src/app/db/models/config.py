"""
配置相关模型
包含: 过滤器分组、过滤规则、RSS解析器、站点配置、同步路径、用户配置、用户RSS配置
"""

from sqlalchemy import BigInteger, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CONFIGFILTERGROUP(Base):
    __tablename__ = "CONFIG_FILTER_GROUP"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    GROUP_NAME: Mapped[str] = mapped_column(String(255))
    IS_DEFAULT: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGFILTERRULES(Base):
    __tablename__ = "CONFIG_FILTER_RULES"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    GROUP_ID: Mapped[int] = mapped_column(Integer, ForeignKey("CONFIG_FILTER_GROUP.ID"), index=True)
    ROLE_NAME: Mapped[str] = mapped_column(String(255))
    PRIORITY: Mapped[str] = mapped_column(String(255))
    INCLUDE: Mapped[str] = mapped_column(Text)
    EXCLUDE: Mapped[str] = mapped_column(Text)
    SIZE_LIMIT: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGRSSPARSER(Base):
    __tablename__ = "CONFIG_RSS_PARSER"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    TYPE: Mapped[str] = mapped_column(String(255))
    FORMAT: Mapped[str] = mapped_column(String(255))
    PARAMS: Mapped[str] = mapped_column(Text)
    NOTE: Mapped[str] = mapped_column(Text, default="")
    SYSDEF: Mapped[str] = mapped_column(String(255))


class CONFIGSITE(Base):
    __tablename__ = "CONFIG_SITE"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255))
    PRI: Mapped[str] = mapped_column(String(255))
    RSSURL: Mapped[str] = mapped_column(String(512))
    SIGNURL: Mapped[str] = mapped_column(String(512))
    COOKIE: Mapped[str | None] = mapped_column(Text, nullable=True)
    API_KEY: Mapped[str | None] = mapped_column(Text, nullable=True)
    BEARER_TOKEN: Mapped[str | None] = mapped_column(Text, nullable=True)
    HEADERS: Mapped[str | None] = mapped_column(Text, nullable=True)
    INCLUDE: Mapped[str] = mapped_column(Text, default="")
    EXCLUDE: Mapped[str] = mapped_column(Text, default="")
    SIZE: Mapped[int] = mapped_column(BigInteger, default=0)
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGSYNCPATHS(Base):
    __tablename__ = "CONFIG_SYNC_PATHS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    SOURCE: Mapped[str] = mapped_column(String(255))
    DEST: Mapped[str] = mapped_column(String(255))
    UNKNOWN: Mapped[str] = mapped_column(String(255))
    MODE: Mapped[str] = mapped_column(String(255))
    OPERATION: Mapped[str | None] = mapped_column(String(50), nullable=True)
    SRC_BACKEND: Mapped[str | None] = mapped_column(String(64), nullable=True)
    DST_BACKEND: Mapped[str | None] = mapped_column(String(64), nullable=True)
    COMPATIBILITY: Mapped[int] = mapped_column(Integer)
    RENAME: Mapped[int] = mapped_column(Integer)
    ENABLED: Mapped[int] = mapped_column(Integer, index=True)
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGUSERS(Base):
    __tablename__ = "CONFIG_USERS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    PASSWORD: Mapped[str] = mapped_column(String(255))
    PRIS: Mapped[str] = mapped_column(String(255))


class CONFIGUSERRSS(Base):
    __tablename__ = "CONFIG_USER_RSS"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    ADDRESS: Mapped[str] = mapped_column(String(255))
    PARSER: Mapped[str] = mapped_column(String(255))
    INTERVAL: Mapped[str] = mapped_column(String(255))
    USES: Mapped[str] = mapped_column(String(255))
    INCLUDE: Mapped[str] = mapped_column(Text)
    EXCLUDE: Mapped[str] = mapped_column(Text)
    FILTER: Mapped[str] = mapped_column(String(255))
    UPDATE_TIME: Mapped[str] = mapped_column(String(255))
    PROCESS_COUNT: Mapped[str] = mapped_column(String(255))
    STATE: Mapped[str] = mapped_column(String(255), index=True)
    SAVE_PATH: Mapped[str] = mapped_column(String(255))
    DOWNLOAD_SETTING: Mapped[int] = mapped_column(Integer, nullable=True)
    RECOGNIZATION: Mapped[str] = mapped_column(String(255))
    OVER_EDITION: Mapped[int] = mapped_column(Integer)
    SITES: Mapped[str] = mapped_column(String(255))
    FILTER_ARGS: Mapped[str] = mapped_column(String(255))
    MEDIAINFOS: Mapped[str] = mapped_column(String(255))
    NOTE: Mapped[str] = mapped_column(Text, default="")


class MEDIASERVER(Base):
    __tablename__ = "MEDIASERVER"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    NAME: Mapped[str] = mapped_column(String(255), index=True)
    ENABLED: Mapped[int] = mapped_column(Integer)
    CONFIG: Mapped[str] = mapped_column(Text)
    IS_DEFAULT: Mapped[int] = mapped_column(Integer)
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGMEDIA(Base):
    """媒体库路径配置表（替代 YAML media 节点中的路径配置）"""

    __tablename__ = "CONFIG_MEDIA"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    MOVIE_PATH: Mapped[str] = mapped_column(Text, default="")
    TV_PATH: Mapped[str] = mapped_column(Text, default="")
    ANIME_PATH: Mapped[str] = mapped_column(Text, default="")
    UNKNOWN_PATH: Mapped[str] = mapped_column(Text, default="")
    MOVIE_BACKEND: Mapped[str | None] = mapped_column(Text, nullable=True)
    TV_BACKEND: Mapped[str | None] = mapped_column(Text, nullable=True)
    ANIME_BACKEND: Mapped[str | None] = mapped_column(Text, nullable=True)
    UNKNOWN_BACKEND: Mapped[str | None] = mapped_column(Text, nullable=True)
    NOTE: Mapped[str] = mapped_column(Text, default="")


class CONFIGCATEGORY(Base):
    """二级分类配置表"""

    __tablename__ = "CONFIG_CATEGORY"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    MEDIA_TYPE: Mapped[str] = mapped_column(String(50), index=True)
    NAME: Mapped[str] = mapped_column(String(255))
    SORT_ORDER: Mapped[int] = mapped_column(Integer, default=0)
    IS_DEFAULT: Mapped[int] = mapped_column(Integer, default=0)


class CONFIGCATEGORYRULE(Base):
    """二级分类规则表"""

    __tablename__ = "CONFIG_CATEGORY_RULE"

    ID: Mapped[int] = mapped_column(Integer, Sequence("ID"), primary_key=True)
    CATEGORY_ID: Mapped[int] = mapped_column(Integer, ForeignKey("CONFIG_CATEGORY.ID"), index=True)
    FIELD: Mapped[str] = mapped_column(String(100))
    VALUE: Mapped[str] = mapped_column(Text)
