"""刮削器 — NFO XML 文件生成器"""

import json
import os
import shutil
import subprocess
import time
import xml.dom.minidom

import defusedxml.minidom  # type: ignore[import-untyped]  # noqa: F401 — XXE防护副作用导入

from app.media.metadata.nfo import render_nfo_extra_tags
from app.media.metadata.registry import registry as metadata_registry
from app.utils import DomUtils


def _create_document():
    return xml.dom.minidom.getDOMImplementation().createDocument(None, None, None)


_SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub", ".vtt")


def _has_external_subtitle(out_path: str, file_name: str) -> bool:
    try:
        names = os.listdir(out_path)
    except OSError:
        return False
    prefix = str(file_name or "").lower()
    return any(name.lower().startswith(prefix) and name.lower().endswith(_SUBTITLE_EXTENSIONS) for name in names)


def _add_tag_once(doc, root, tag: str) -> None:
    existing = {str(node.firstChild.nodeValue if node.firstChild else "") for node in root.getElementsByTagName("tag")}
    if tag not in existing:
        DomUtils.add_node(doc, root, "tag", tag)


class NfoGenerator:
    """NFO 文件生成器 — 负责生成电影/电视剧/季/集的 NFO XML"""

    def __init__(self, image_downloader):
        self._downloader = image_downloader

    def gen_movie_nfo(self, tmdbinfo, directors, actors, scraper_nfo, out_path, file_name):
        """生成电影 NFO 文件"""
        doc = _create_document()
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
        doc = _create_document()
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
        doc = _create_document()
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
        doc = _create_document()
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
                doc, root, "year", (episode_detail.get("air_date") or "")[:4] if episode_detail.get("air_date") else ""
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
                for alias in actor.get("aliases") or []:
                    DomUtils.add_node(doc, xactor, "alias", alias)
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

    # ---------- snapshot 渲染（ADR-025） ----------

    def gen_movie_nfo_from_snapshot(self, snapshot, scraper_nfo, out_path, file_name):
        """从 MediaMetadata 快照生成电影 NFO."""
        if getattr(snapshot, "content_profile", "") == "adult":
            # 成人自定义画像必须写标题/简介/演员，不能因用户旧配置只在 NFO 留番号。
            scraper_nfo = {**scraper_nfo, "basic": True, "credits": True}
        doc = _create_document()
        root = DomUtils.add_node(doc, doc, "movie")
        self._gen_snapshot_common(snapshot, doc, root, scraper_nfo)
        if scraper_nfo.get("basic"):
            DomUtils.add_node(doc, root, "title", _snapshot_value(snapshot, "title"))
            DomUtils.add_node(doc, root, "originaltitle", _snapshot_value(snapshot, "original_title"))
            release = _snapshot_value(snapshot, "release_date")
            DomUtils.add_node(doc, root, "premiered", release)
            DomUtils.add_node(doc, root, "year", _snapshot_value(snapshot, "year") or str(release)[:4])
        self._append_fileinfo(doc, root, out_path, file_name)
        if _has_external_subtitle(out_path, file_name):
            _add_tag_once(doc, root, "中字")
        self._downloader.save_nfo(doc, os.path.join(out_path, f"{file_name}.nfo"))

    def _append_fileinfo(self, doc, root, out_path, file_name):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return
        if not os.path.isdir(out_path):
            return
        try:
            names = os.listdir(out_path)
        except OSError:
            return
        candidates = [
            os.path.join(out_path, item)
            for item in names
            if item.startswith(file_name) and item.lower().endswith((".mp4", ".mkv", ".avi", ".wmv", ".ts", ".m2ts"))
        ]
        if not candidates:
            return
        try:
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", candidates[0]],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            data = json.loads(result.stdout or "{}")
        except (OSError, subprocess.SubprocessError, ValueError):
            return
        streams = data.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if not video:
            return
        fileinfo = DomUtils.add_node(doc, root, "fileinfo")
        details = DomUtils.add_node(doc, fileinfo, "streamdetails")
        node = DomUtils.add_node(doc, details, "video")
        DomUtils.add_node(doc, node, "codec", video.get("codec_name") or "")
        DomUtils.add_node(doc, node, "micodec", video.get("codec_name") or "")
        DomUtils.add_node(doc, node, "bitrate", video.get("bit_rate") or "")
        DomUtils.add_node(doc, node, "width", video.get("width") or "")
        DomUtils.add_node(doc, node, "height", video.get("height") or "")
        aspect = "16:9" if int(video.get("width") or 0) > int(video.get("height") or 0) else "4:3"
        DomUtils.add_node(doc, node, "aspect", aspect)
        DomUtils.add_node(doc, node, "aspectratio", aspect)
        DomUtils.add_node(doc, node, "framerate", video.get("avg_frame_rate") or "")
        DomUtils.add_node(doc, node, "duration", (data.get("format") or {}).get("duration") or "")
        DomUtils.add_node(doc, node, "durationinseconds", (data.get("format") or {}).get("duration") or "")
        if audio:
            audio_node = DomUtils.add_node(doc, details, "audio")
            DomUtils.add_node(doc, audio_node, "codec", audio.get("codec_name") or "")
            DomUtils.add_node(doc, audio_node, "micodec", audio.get("codec_name") or "")
            DomUtils.add_node(doc, audio_node, "bitrate", audio.get("bit_rate") or "")
            DomUtils.add_node(doc, audio_node, "channels", audio.get("channels") or "")
            DomUtils.add_node(doc, audio_node, "samplingrate", audio.get("sample_rate") or "")

    def gen_tv_nfo_from_snapshot(
        self,
        snapshot,
        scraper_nfo,
        out_path,
        *,
        show_title: str = "",
    ):
        """从 MediaMetadata 快照生成 tvshow NFO；剧名使用剧集级标题而非季标题."""
        doc = _create_document()
        root = DomUtils.add_node(doc, doc, "tvshow")
        self._gen_snapshot_common(snapshot, doc, root, scraper_nfo)
        if scraper_nfo.get("basic"):
            DomUtils.add_node(
                doc,
                root,
                "title",
                show_title or _snapshot_value(snapshot, "title"),
            )
            DomUtils.add_node(doc, root, "originaltitle", _snapshot_value(snapshot, "original_title"))
            release = _snapshot_value(snapshot, "release_date")
            DomUtils.add_node(doc, root, "premiered", release)
            DomUtils.add_node(doc, root, "year", _snapshot_value(snapshot, "year") or str(release)[:4])
        self._downloader.save_nfo(doc, os.path.join(out_path, "tvshow.nfo"))

    def gen_season_nfo_from_snapshot(self, season, season_number, out_path):
        """从 SeasonRecord 生成 season.nfo."""
        doc = _create_document()
        root = DomUtils.add_node(doc, doc, "season")
        DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
        xplot = DomUtils.add_node(doc, root, "plot")
        xplot.appendChild(doc.createCDATASection(season.overview or ""))
        xoutline = DomUtils.add_node(doc, root, "outline")
        xoutline.appendChild(doc.createCDATASection(season.overview or ""))
        DomUtils.add_node(doc, root, "title", season.title or f"季 {season_number}")
        DomUtils.add_node(doc, root, "premiered", season.air_date or "")
        DomUtils.add_node(doc, root, "releasedate", season.air_date or "")
        DomUtils.add_node(doc, root, "year", (season.air_date or "")[:4])
        DomUtils.add_node(doc, root, "seasonnumber", season_number)
        self._downloader.save_nfo(doc, os.path.join(out_path, "season.nfo"))

    def gen_episode_nfo_from_snapshot(self, snapshot, episode, scraper_nfo, season, out_path, file_name):
        """从 EpisodeRecord 生成分集 NFO."""
        doc = _create_document()
        root = DomUtils.add_node(doc, doc, "episodedetails")
        if scraper_nfo.get("episode_basic"):
            DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
            self._write_snapshot_uniqueids(snapshot, doc, root)
            DomUtils.add_node(doc, root, "title", episode.title or f"第 {episode.episode_number} 集")
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(episode.overview or ""))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(episode.overview or ""))
            DomUtils.add_node(doc, root, "aired", episode.air_date or "")
            DomUtils.add_node(doc, root, "year", (episode.air_date or "")[:4])
            DomUtils.add_node(doc, root, "season", season)
            DomUtils.add_node(doc, root, "episode", episode.episode_number)
            DomUtils.add_node(doc, root, "rating", episode.vote_average or "0")
        self._downloader.save_nfo(doc, os.path.join(out_path, f"{file_name}.nfo"))

    def _gen_snapshot_common(self, snapshot, doc, root, scraper_nfo):
        if scraper_nfo.get("basic"):
            DomUtils.add_node(doc, root, "dateadded", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
            self._write_snapshot_uniqueids(snapshot, doc, root)
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(_snapshot_value(snapshot, "overview")))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(_snapshot_value(snapshot, "overview")))
            for genre in snapshot.genres:
                DomUtils.add_node(doc, root, "genre", genre)
            rating = _snapshot_rating(snapshot)
            if rating is not None:
                DomUtils.add_node(doc, root, "rating", rating)
            votes = _snapshot_value(snapshot, "votes", "") or (snapshot.extra or {}).get("votes")
            if votes:
                DomUtils.add_node(doc, root, "votes", votes)
            if snapshot.ratings:
                ratings_node = DomUtils.add_node(doc, root, "ratings")
                for provider_key, provider_value in snapshot.ratings.items():
                    rating_node = DomUtils.add_node(doc, ratings_node, "rating")
                    rating_node.setAttribute("name", str(provider_key))
                    rating_node.setAttribute("max", _rating_max(provider_key))
                    if provider_key == snapshot.primary_provider:
                        rating_node.setAttribute("default", "true")
                    value = float(provider_value)
                    if value > 10:
                        value = value / 100
                    DomUtils.add_node(doc, rating_node, "value", value)
                    if votes:
                        DomUtils.add_node(doc, rating_node, "votes", votes)
            runtime = _snapshot_value(snapshot, "runtime", "")
            if runtime:
                DomUtils.add_node(doc, root, "runtime", runtime)
            for studio in snapshot.studios:
                DomUtils.add_node(doc, root, "studio", studio)
            for label in snapshot.labels:
                DomUtils.add_node(doc, root, "tag", label)
            for series in snapshot.series:
                set_node = DomUtils.add_node(doc, root, "set")
                DomUtils.add_node(doc, set_node, "name", series)
        # 插件 NFO 模板不依赖 basic 开关，只要生成了 NFO 就应用。
        for tag, value in render_nfo_extra_tags(snapshot).items():
            if isinstance(value, list):
                for entry in value:
                    DomUtils.add_node(doc, root, tag, entry)
            elif value not in (None, ""):
                DomUtils.add_node(doc, root, tag, value)
        if scraper_nfo.get("credits"):
            actor_images = (snapshot.extra or {}).get("actor_images") or {}
            fallback_actors = (snapshot.extra or {}).get("actor_fallback") or []
            for credit in snapshot.credits:
                if credit.role == "director":
                    node = DomUtils.add_node(doc, root, "director", credit.name)
                    if credit.provider == "tmdb" and credit.external_id:
                        node.setAttribute("tmdbid", credit.external_id)
                elif credit.role == "actor":
                    actor = DomUtils.add_node(doc, root, "actor")
                    DomUtils.add_node(doc, actor, "name", credit.name)
                    for alias in credit.aliases:
                        DomUtils.add_node(doc, actor, "alias", alias)
                    DomUtils.add_node(doc, actor, "type", "Actor")
                    DomUtils.add_node(doc, actor, "role", credit.character or "")
                    DomUtils.add_node(doc, actor, "order", credit.order)
                    if credit.provider == "tmdb" and credit.external_id:
                        DomUtils.add_node(doc, actor, "tmdbid", credit.external_id)
                    if credit.image_url:
                        DomUtils.add_node(doc, actor, "thumb", credit.image_url)
                        DomUtils.add_node(doc, actor, "profile", credit.image_url)
            if not snapshot.credits and fallback_actors:
                actor_aliases = (snapshot.extra or {}).get("actor_aliases") or {}
                for name in fallback_actors:
                    actor = DomUtils.add_node(doc, root, "actor")
                    DomUtils.add_node(doc, actor, "name", name)
                    for alias in actor_aliases.get(name) or []:
                        DomUtils.add_node(doc, actor, "alias", alias)
                    DomUtils.add_node(doc, actor, "type", "Actor")
                    image = actor_images.get(name)
                    if image:
                        DomUtils.add_node(doc, actor, "thumb", image)
                        DomUtils.add_node(doc, actor, "profile", image)

    def _write_snapshot_uniqueids(self, snapshot, doc, root):
        primary = snapshot.primary_provider
        primary_desc = getattr(metadata_registry.get_provider(primary), "descriptor", None)
        if getattr(primary_desc, "virtual", False):
            primary = str(getattr(primary_desc, "uniqueid_fallback", "") or "")
        refs = []
        seen = set()
        for ref in snapshot.refs:
            provider_desc = getattr(metadata_registry.get_provider(ref.provider), "descriptor", None)
            if getattr(provider_desc, "virtual", False):
                continue
            if ref.provider in seen:
                continue
            seen.add(ref.provider)
            refs.append(ref)
        default_provider = primary if any(ref.provider == primary for ref in refs) else None
        if default_provider is None:
            if any(ref.provider == "tmdb" for ref in refs):
                default_provider = "tmdb"
            else:
                default_provider = refs[0].provider if refs else ""
        for ref in refs:
            uniqueid = DomUtils.add_node(doc, root, "uniqueid", ref.external_id)
            uniqueid.setAttribute("type", ref.provider)
            uniqueid.setAttribute("default", "true" if ref.provider == default_provider else "false")
            if ref.provider == "tmdb":
                DomUtils.add_node(doc, root, "tmdbid", ref.external_id)
            elif ref.provider == "imdb":
                DomUtils.add_node(doc, root, "imdbid", ref.external_id)
            elif ref.provider == "tvdb":
                DomUtils.add_node(doc, root, "tvdbid", ref.external_id)


def _rating_max(provider: object) -> str:
    item = metadata_registry.get_provider(str(provider))
    return str(getattr(getattr(item, "descriptor", None), "rating_max", 10) or 10)


def _snapshot_value(snapshot, name, default=""):
    field = snapshot.fields.get(name)
    if field is None or field.value is None:
        return default
    return field.value


def _snapshot_rating(snapshot):
    if not snapshot.ratings:
        return None
    if snapshot.primary_provider in snapshot.ratings:
        value = snapshot.ratings[snapshot.primary_provider]
    elif "tmdb" in snapshot.ratings:
        value = snapshot.ratings["tmdb"]
    else:
        value = next(iter(snapshot.ratings.values()))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return number / 100 if number > 10 else number
