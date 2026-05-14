"""刮削器 — NFO XML 文件生成器"""

import os
import time
from xml.dom import minidom

from app.utils import DomUtils


class NfoGenerator:
    """NFO 文件生成器 — 负责生成电影/电视剧/季/集的 NFO XML"""

    def __init__(self, image_downloader):
        self._downloader = image_downloader

    def gen_movie_nfo(self, tmdbinfo, directors, actors, scraper_nfo, out_path, file_name):
        """生成电影 NFO 文件"""
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "movie")
        doc = self._gen_common_nfo(tmdbinfo, directors, actors, doc, root, scraper_nfo)
        if scraper_nfo.get("basic"):
            DomUtils.add_node(doc, root, "title", tmdbinfo.get("title") or "")
            DomUtils.add_node(doc, root, "originaltitle", tmdbinfo.get("original_title") or "")
            DomUtils.add_node(doc, root, "premiered", tmdbinfo.get("release_date") or "")
            DomUtils.add_node(
                doc, root, "year", tmdbinfo.get("release_date")[:4] if tmdbinfo.get("release_date") else ""
            )
        self._downloader.save_nfo(doc, os.path.join(out_path, f"{file_name}.nfo"))

    def gen_tv_nfo(self, tmdbinfo, directors, actors, scraper_nfo, out_path):
        """生成电视剧 NFO 文件"""
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "tvshow")
        doc = self._gen_common_nfo(tmdbinfo, directors, actors, doc, root, scraper_nfo)
        if scraper_nfo.get("basic"):
            DomUtils.add_node(doc, root, "title", tmdbinfo.get("name") or "")
            DomUtils.add_node(doc, root, "originaltitle", tmdbinfo.get("original_name") or "")
            DomUtils.add_node(doc, root, "premiered", tmdbinfo.get("first_air_date") or "")
            DomUtils.add_node(
                doc, root, "year", tmdbinfo.get("first_air_date")[:4] if tmdbinfo.get("first_air_date") else ""
            )
            DomUtils.add_node(doc, root, "season", "-1")
            DomUtils.add_node(doc, root, "episode", "-1")
        self._downloader.save_nfo(doc, os.path.join(out_path, "tvshow.nfo"))

    def gen_season_nfo(self, seasoninfo, season, out_path):
        """生成季 NFO 文件"""
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "season")
        DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
        xplot = DomUtils.add_node(doc, root, "plot")
        xplot.appendChild(doc.createCDATASection(seasoninfo.get("overview") or ""))
        xoutline = DomUtils.add_node(doc, root, "outline")
        xoutline.appendChild(doc.createCDATASection(seasoninfo.get("overview") or ""))
        DomUtils.add_node(doc, root, "title", f"季 {season}")
        DomUtils.add_node(doc, root, "premiered", seasoninfo.get("air_date") or "")
        DomUtils.add_node(doc, root, "releasedate", seasoninfo.get("air_date") or "")
        DomUtils.add_node(doc, root, "year", seasoninfo.get("air_date")[:4] if seasoninfo.get("air_date") else "")
        DomUtils.add_node(doc, root, "seasonnumber", season)
        self._downloader.save_nfo(doc, os.path.join(out_path, "season.nfo"))

    def gen_episode_nfo(self, seasoninfo, scraper_nfo, season, episode, out_path, file_name):
        """生成剧集 NFO 文件"""
        episode_detail = {}
        for ep_info in seasoninfo.get("episodes") or []:
            if int(ep_info.get("episode_number")) == int(episode):
                episode_detail = ep_info
        if not episode_detail:
            return
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "episodedetails")
        if scraper_nfo.get("episode_basic"):
            DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
            uniqueid = DomUtils.add_node(doc, root, "uniqueid", episode_detail.get("id") or "")
            uniqueid.setAttribute("type", "tmdb")
            uniqueid.setAttribute("default", "true")
            DomUtils.add_node(doc, root, "tmdbid", episode_detail.get("id") or "")
            DomUtils.add_node(doc, root, "title", episode_detail.get("name") or f"第 {episode} 集")
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(episode_detail.get("overview") or ""))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(episode_detail.get("overview") or ""))
            DomUtils.add_node(doc, root, "aired", episode_detail.get("air_date") or "")
            DomUtils.add_node(
                doc, root, "year", episode_detail.get("air_date")[:4] if episode_detail.get("air_date") else ""
            )
            DomUtils.add_node(doc, root, "season", season)
            DomUtils.add_node(doc, root, "episode", episode)
            DomUtils.add_node(doc, root, "rating", episode_detail.get("vote_average") or "0")
        if scraper_nfo.get("episode_credits"):
            for director in episode_detail.get("crew") or []:
                if director.get("known_for_department") == "Directing":
                    xdirector = DomUtils.add_node(doc, root, "director", director.get("name") or "")
                    xdirector.setAttribute("tmdbid", str(director.get("id") or ""))
            for actor in episode_detail.get("guest_stars") or []:
                if actor.get("known_for_department") == "Acting":
                    xactor = DomUtils.add_node(doc, root, "actor")
                    DomUtils.add_node(doc, xactor, "name", actor.get("name") or "")
                    DomUtils.add_node(doc, xactor, "type", "Actor")
                    DomUtils.add_node(doc, xactor, "tmdbid", actor.get("id") or "")
        self._downloader.save_nfo(doc, os.path.join(out_path, f"{file_name}.nfo"))

    def _gen_common_nfo(self, tmdbinfo, directors, actors, doc, root, scraper_nfo):
        """NFO 公共部分（基础信息 + 演职人员 + 风格/评分）"""
        if scraper_nfo.get("basic"):
            DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
            DomUtils.add_node(doc, root, "tmdbid", tmdbinfo.get("id") or "")
            uniqueid_tmdb = DomUtils.add_node(doc, root, "uniqueid", tmdbinfo.get("id") or "")
            uniqueid_tmdb.setAttribute("type", "tmdb")
            uniqueid_tmdb.setAttribute("default", "true")
            if tmdbinfo.get("external_ids"):
                tvdbid = tmdbinfo.get("external_ids", {}).get("tvdb_id", 0)
                if tvdbid:
                    DomUtils.add_node(doc, root, "tvdbid", tvdbid)
                    uniqueid_tvdb = DomUtils.add_node(doc, root, "uniqueid", tvdbid)
                    uniqueid_tvdb.setAttribute("type", "tvdb")
                imdbid = tmdbinfo.get("external_ids", {}).get("imdb_id", "")
                if imdbid:
                    DomUtils.add_node(doc, root, "imdbid", imdbid)
                    uniqueid_imdb = DomUtils.add_node(doc, root, "uniqueid", imdbid)
                    uniqueid_imdb.setAttribute("type", "imdb")
                    uniqueid_imdb.setAttribute("default", "true")
                    uniqueid_tmdb.setAttribute("default", "false")
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
        if scraper_nfo.get("credits"):
            for director in directors:
                xdirector = DomUtils.add_node(doc, root, "director", director.get("name") or "")
                xdirector.setAttribute("tmdbid", str(director.get("id") or ""))
            for actor in actors:
                xactor = DomUtils.add_node(doc, root, "actor")
                DomUtils.add_node(doc, xactor, "name", actor.get("name") or "")
                DomUtils.add_node(doc, xactor, "type", "Actor")
                DomUtils.add_node(doc, xactor, "role", actor.get("role") or "")
                DomUtils.add_node(doc, xactor, "order", actor.get("order") if actor.get("order") is not None else "")
                DomUtils.add_node(doc, xactor, "tmdbid", actor.get("id") or "")
                DomUtils.add_node(doc, xactor, "thumb", actor.get("image"))
                DomUtils.add_node(doc, xactor, "profile", actor.get("profile"))
        if scraper_nfo.get("basic"):
            for genre in tmdbinfo.get("genres") or []:
                DomUtils.add_node(doc, root, "genre", genre.get("name") or "")
            DomUtils.add_node(doc, root, "rating", tmdbinfo.get("vote_average") or "0")
        return doc
