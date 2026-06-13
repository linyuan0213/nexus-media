"""
动漫标题解析 — 季、集、年份解析
"""

from app.domain.mediatypes import MediaType
from app.utils import ExceptionUtils


def parse_year(info, anitopy_info):
    """解析年份"""
    year = anitopy_info.get("anime_year")
    if str(year).isdigit():
        info.year = str(year)


def parse_season(info, anitopy_info):
    """解析季号"""
    anime_season = anitopy_info.get("anime_season")
    if isinstance(anime_season, list):
        begin_season = anime_season[0] if len(anime_season) == 1 else anime_season[0]
        end_season = None if len(anime_season) == 1 else anime_season[-1]
    elif anime_season:
        begin_season = anime_season
        end_season = None
    else:
        begin_season = None
        end_season = None
    if begin_season:
        info.begin_season = int(begin_season)
        if end_season and int(end_season) != info.begin_season:
            info.end_season = int(end_season)
            info.total_seasons = (info.end_season - info.begin_season) + 1
        else:
            info.total_seasons = 1
        info.type = MediaType.TV


def parse_episode(info, anitopy_info):
    """解析集号"""
    episode_number = anitopy_info.get("episode_number")
    if isinstance(episode_number, list):
        begin_episode = episode_number[0] if len(episode_number) == 1 else episode_number[0]
        end_episode = None if len(episode_number) == 1 else episode_number[-1]
    elif episode_number:
        begin_episode = episode_number
        end_episode = None
    else:
        begin_episode = None
        end_episode = None
    if begin_episode:
        try:
            info.begin_episode = int(begin_episode)
            if end_episode and int(end_episode) != info.begin_episode:
                info.end_episode = int(end_episode)
                info.total_episodes = (info.end_episode - info.begin_episode) + 1
            else:
                info.total_episodes = 1
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            info.begin_episode = None
            info.end_episode = None
        info.type = MediaType.TV


def parse_type(info, anitopy_info):
    """解析类型（TV/Movie）"""
    if not info.type:
        anime_type = anitopy_info.get("anime_type")
        if isinstance(anime_type, list):
            anime_type = anime_type[0]
        if anime_type and anime_type.upper() == "TV":
            info.type = MediaType.TV
        else:
            info.type = MediaType.MOVIE
