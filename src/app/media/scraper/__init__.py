"""app.media.scraper — 媒体元数据刮削模块

重构后架构:
  - Scraper           — 主协调类（保持原有 API）
  - NfoGenerator      — NFO XML 生成
  - ImageDownloader   — 图片下载与文件保存
  - MediaLibrary      — 媒体库文件遍历与 NFO 读取
  - ChineseCredits    — 豆瓣演职人员中文名匹配
"""

import json
import os
import re
import shutil
import threading
import time

from PIL import Image

import log
from app.core.module_config import ModuleConf
from app.core.settings import settings
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.domain.enums import SystemConfigKey
from app.domain.media_types import ProviderMediaType
from app.infrastructure.ffmpeg import FfmpegProcessor
from app.infrastructure.image_proxy import ImageProxy
from app.infrastructure.system_config import SystemConfig
from app.infrastructure.temp import temp_manager
from app.media.display_image_policy import unwrap_display_image_url
from app.media.fanart import Fanart
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.media.metadata.images import ImageResolver
from app.media.metadata.models import Credit, ImageAsset, MediaMetadata
from app.media.metadata.parsing import ParserChain
from app.media.parser._metainfo import meta_info
from app.media.service import MediaService
from app.utils import ExceptionUtils
from app.utils.json_utils import JsonUtils

from .chinese_credits import ChineseCredits
from .image_downloader import ImageDownloader
from .media_library import MediaLibrary
from .nfo_generator import NfoGenerator
from .poster_quality import has_legacy_watermark_marker, synthetic_poster_path
from .poster_quality import is_placeholder_image as _poster_is_placeholder
from .processor_registry import scraper_processor_registry

_PART_SUFFIX_RE = re.compile(r"(?i)[-_. ]?(?:cd|part|pt|disk|disc|dvd)\s*[1-9a-d]$")


def _nfo_base_name(file_path: str) -> str:
    """去掉 cd1/part1 等分段后缀，Emby 会把这些文件堆叠为一个影片."""
    stem = os.path.splitext(os.path.basename(file_path))[0]
    return _PART_SUFFIX_RE.sub("", stem)


class Scraper:
    """媒体元数据刮削器 — 生成 NFO 文件、下载图片"""

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        media_service: MediaService,
        system_config: SystemConfig | None = None,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self.media = media_service
        self._metadata_gateway = metadata_gateway
        self.fanart = Fanart()
        self._system_config = system_config or SystemConfig()
        self._scraper_flag = False
        self._scraper_nfo = {}
        self._scraper_pic = {}
        self._local = threading.local()
        self._rmt_mode = None
        self._temp_path = temp_manager.create_subdir("scraper")
        self._init_config()
        self._downloader = ImageDownloader(self._temp_path)
        self._nfo_gen = NfoGenerator(self._downloader, metadata_gateway=self._metadata_gateway)
        self._images = ImageResolver()
        self._credits = ChineseCredits(self._metadata_gateway)

    @property
    def _metadata(self):
        return self._metadata_gateway

    def _metadata_context(self, content_profile: str | None = None) -> MetadataContext:
        return MetadataContext(
            purpose="scrape",
            allow_private=True,
            content_profile=str(content_profile or "default"),
        )

    def _lookup(self, provider: str, external_id: str, **kwargs):
        if self._metadata_gateway is None:
            return None
        kwargs.pop("allow_private", None)
        kwargs.pop("permissions", None)
        kwargs["context"] = self._metadata_context(kwargs.get("content_profile"))
        return self._metadata_gateway.lookup(provider, external_id, **kwargs)

    def _search(self, **kwargs):
        if self._metadata_gateway is None:
            return []
        kwargs["context"] = self._metadata_context(kwargs.get("content_profile"))
        return self._metadata_gateway.search(**kwargs)

    def _compose(self, media_info, **kwargs):
        if self._metadata_gateway is None:
            return None
        kwargs["context"] = self._metadata_context(kwargs.get("content_profile"))
        return self._metadata_gateway.compose_for_media(media_info, **kwargs)

    def _latest_snapshot(self, media_info):
        if self._metadata_gateway is None:
            return None
        return self._metadata_gateway.latest_snapshot_for_media(
            media_info,
            context=self._metadata_context(getattr(media_info, "content_profile", None)),
        )

    def _identify_anchor(self, media_info, *, policy: str | None = None):
        if self._metadata_gateway is None:
            return False
        return self._metadata_gateway.identify_anchor(
            media_info,
            context=self._metadata_context(getattr(media_info, "content_profile", None)),
            policy=policy,
        )

    def _init_config(self):
        self._scraper_flag = (settings.get("media") or {}).get("nfo_poster")
        self._legacy_tmdb_fallback = bool((settings.get("media") or {}).get("legacy_tmdb_fallback", True))
        scraper_conf = self._system_config.get(SystemConfigKey.UserScraperConf)
        if isinstance(scraper_conf, str):
            try:
                scraper_conf = JsonUtils.loads(scraper_conf)
                # 兼容旧版双重 JSON 编码（set_scraper_config 曾用 json.dumps 预编码）
                if isinstance(scraper_conf, str):
                    scraper_conf = JsonUtils.loads(scraper_conf)
            except Exception:
                scraper_conf = None
        if isinstance(scraper_conf, dict):
            self._scraper_nfo = scraper_conf.get("scraper_nfo") or {}
            self._scraper_pic = scraper_conf.get("scraper_pic") or {}

    def _target_exists(self, path: str, dst_backend=None) -> bool:
        if dst_backend is not None:
            return bool(dst_backend.exists(path))
        return os.path.exists(path)

    def _read_text(self, path: str, dst_backend=None) -> str:
        try:
            if dst_backend is not None:
                with dst_backend.read_stream(path) as stream:
                    return stream.read(200_000).decode("utf-8", errors="ignore")
            with open(path, encoding="utf-8", errors="ignore") as handle:
                return handle.read(200_000)
        except OSError:
            return ""

    @staticmethod
    def _nfo_has_metadata(text: str) -> bool:
        """旧版 NFO 可能只有文件信息，plot/title 等核心字段为空，仍视为未刮削."""
        for tag in ("plot", "outline", "year", "premiered", "customrating", "num", "maker", "label"):
            match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.S)
            if match and match.group(1).strip():
                return True
        rating = re.search(r"<rating[^>]*>(.*?)</rating>", text, re.S)
        return bool(rating and rating.group(1).strip() not in ("", "0"))

    def _has_scraped_metadata(self, file: str, dst_backend=None) -> bool:
        """判断单个文件是否已具备当前配置要求的 NFO 与图片，供增量刮削跳过."""
        media_info = self._profile_media_info(file) or meta_info(os.path.basename(file))
        media_type = getattr(media_info, "type", None) or ProviderMediaType.MOVIE
        is_tv = media_type in {ProviderMediaType.SERIES, ProviderMediaType.ANIME}
        if is_tv and media_type == ProviderMediaType.SERIES:
            explicit_series = bool(
                re.search(
                    r"(?i)(?:^|[.\s_\-\[])(?:s\d{1,2}(?:e\d{1,3})?|season[.\s]*\d+|第\s*\d+\s*季)",
                    os.path.basename(file),
                )
            )
            if not explicit_series:
                # 番号文件名常被误判为 TV；没有明确季集标记时按电影处理。
                is_tv = False
        nfo_conf = self._scraper_nfo.get("tv" if is_tv else "movie", {})
        pic_conf = self._scraper_pic.get("tv" if is_tv else "movie", {})
        nfo_required = any(
            bool(nfo_conf.get(key)) for key in ("basic", "credits", "season_basic", "episode_basic", "episode_credits")
        )
        pic_required = any(
            bool(pic_conf.get(key)) for key in ("poster", "fanart", "backdrop", "logo", "thumb", "episode_thumb")
        )
        if not nfo_required and not pic_required:
            return True

        file_dir = os.path.dirname(file)
        parent_dir = os.path.dirname(file_dir)
        stem = os.path.splitext(file)[0]
        nfo_candidates = [f"{stem}.nfo"]
        if is_tv:
            nfo_candidates.extend([os.path.join(file_dir, "season.nfo"), os.path.join(parent_dir, "tvshow.nfo")])
        else:
            nfo_candidates.append(os.path.join(file_dir, "movie.nfo"))
        if nfo_required:
            nfo_text = ""
            for path in nfo_candidates:
                if self._target_exists(path, dst_backend):
                    nfo_text = self._read_text(path, dst_backend)
                    break
            if not self._nfo_has_metadata(nfo_text):
                return False

        image_groups: list[tuple[str, ...]] = []
        # 只把核心封面作为完成条件；logo/thumb/background 等属于可选附加图，
        # 来源没有时不能反复判定为“刮削失败”。
        if pic_conf.get("poster"):
            image_groups.append(("poster",))
        elif pic_conf.get("fanart") or pic_conf.get("backdrop"):
            image_groups.append(("fanart", "backdrop"))
        if pic_required and image_groups:
            roots = [file_dir, parent_dir] if is_tv else [file_dir]
            for names in image_groups:
                # 海报/背景/缩略图必须分别存在；有 fanart 不代表 poster 已完成。
                if not any(
                    self._target_exists(os.path.join(root, f"{name}{ext}"), dst_backend)
                    for root in roots
                    for name in names
                    for ext in (".jpg", ".jpeg", ".png", ".webp")
                ):
                    return False
        return True

    def profile_media_info(self, file_path: str):
        """公开的画像媒体信息构造，供媒体库插件构造刷新事件."""
        return self._profile_media_info(file_path)

    @staticmethod
    def _profile_media_info(file_path: str):
        """用插件注册的 ParserProfile 从文件名构造媒体信息."""
        parsed = ParserChain().extract(os.path.basename(file_path))
        if parsed is None or not getattr(parsed, "content_profile", None):
            return None
        code = getattr(parsed, "anchor_external_id", None) or os.path.basename(file_path)
        media_info = meta_info(code, mtype=getattr(parsed, "type", None) or ProviderMediaType.MOVIE)
        media_info.content_profile = parsed.content_profile
        media_info.anchor_provider = getattr(parsed, "anchor_provider", "") or ""
        media_info.anchor_external_id = getattr(parsed, "anchor_external_id", "") or ""
        return media_info

    def _nfo_needs_rewrite(self, dir_path: str, file_name: str, media_type) -> bool:
        """已有 NFO 但缺少核心元数据时，增量模式也必须重写."""
        is_tv = media_type in {ProviderMediaType.SERIES, ProviderMediaType.ANIME}
        candidates = [os.path.join(dir_path, f"{file_name}.nfo")]
        if is_tv:
            candidates.extend([os.path.join(dir_path, "tvshow.nfo"), os.path.join(dir_path, "season.nfo")])
        else:
            candidates.append(os.path.join(dir_path, "movie.nfo"))
        for nfo_path in candidates:
            if self._exists(nfo_path) and not self._nfo_has_metadata(self._read_text(nfo_path)):
                return True
        return False

    def _write_identity_nfo(self, file: str, media_info, force_nfo: bool) -> None:
        """元数据合成失败时至少写入识别出的番号标题，避免留下空 NFO."""
        dir_path = os.path.dirname(file)
        file_name = _nfo_base_name(file)
        nfo_path = os.path.join(dir_path, f"{file_name}.nfo")
        if not force_nfo and self._exists(nfo_path) and self._nfo_has_metadata(self._read_text(nfo_path)):
            return
        title = self._download_history_title(file) or str(getattr(media_info, "title", "") or "").strip() or file_name
        year = str(getattr(media_info, "year", "") or "")
        scraper_nfo = {**self._scraper_nfo.get("movie", {}), "basic": True}
        try:
            self._nfo_gen.gen_movie_nfo(
                {"title": title, "original_title": title, "release_date": year},
                [],
                [],
                scraper_nfo,
                dir_path,
                file_name,
            )
            log.info(f"[Scraper]{file} 已写入基础 NFO 标题：{title}")
        except Exception as e:  # noqa: BLE001 - 兜底失败不阻断其他文件
            log.warn(f"[Scraper]{file} 写入基础 NFO 失败: {e}")

    def folder_scraper(self, path, exclude_path=None, mode=None, dst_backend=None):
        """刮削指定文件夹或文件"""
        try:
            self._init_config()
            only_missing = mode in ("missing", "no_force")
            force_nfo = mode in ["force_nfo", "force_all"]
            force_pic = mode == "force_all"
            force_refresh = mode in ("force_nfo", "force_all")
            self._downloader.set_dst_backend(dst_backend)
            files = list(MediaLibrary.get_library_files(path, exclude_path, backend=dst_backend))
            log.info(f"[Scraper]发现 {len(files)} 个待刮削文件")
            for file in files:
                if not file:
                    continue
                if only_missing and self._has_scraped_metadata(file, dst_backend):
                    log.debug(f"[Scraper]跳过已完成元数据：{file}")
                    continue
                log.info(f"[Scraper]开始刮削媒体库文件：{file} ...")
                mi = meta_info(os.path.basename(file))
                profile_info = self._profile_media_info(file)
                if profile_info is not None and self._metadata_gateway is not None:
                    snapshot = None if force_refresh else self._latest_snapshot(profile_info)
                    if snapshot is None:
                        snapshot = self._compose(
                            profile_info,
                            with_episodes=True,
                            persist=True,
                            max_age_seconds=0 if force_refresh else 1800,
                        )
                    if snapshot is None and force_refresh:
                        snapshot = self._latest_snapshot(profile_info)
                        if snapshot is not None:
                            log.warn(f"[Scraper]{file} 强制重刮合成失败，回退最近快照")
                    if snapshot is not None:
                        scraped = self.gen_snapshot_files(
                            snapshot=snapshot,
                            media=profile_info,
                            dir_path=os.path.dirname(file),
                            file_name=_nfo_base_name(file),
                            file_ext=os.path.splitext(file)[-1],
                            force_nfo=force_nfo,
                            force_pic=force_pic,
                            dst_backend=dst_backend,
                        )
                        if scraped:
                            log.info(f"[Scraper]{file} 插件画像快照刮削完成")
                            continue
                        log.error(f"[Scraper]{file} 插件画像快照刮削未生成完整 NFO/图片")
                    log.warn(f"[Scraper]{file} 插件画像无法合成元数据快照")
                    self._write_identity_nfo(file, profile_info, force_nfo)
                    continue
                standard_snapshot = self._compose_standard_snapshot(file, mi)
                if standard_snapshot is not None:
                    scraped = self.gen_snapshot_files(
                        snapshot=standard_snapshot,
                        media=mi,
                        dir_path=os.path.dirname(file),
                        file_name=_nfo_base_name(file),
                        file_ext=os.path.splitext(file)[-1],
                        force_nfo=force_nfo,
                        force_pic=force_pic,
                        dst_backend=dst_backend,
                    )
                    if scraped:
                        log.info(f"[Scraper]{file} 普通媒体快照刮削完成")
                    else:
                        log.error(f"[Scraper]{file} 普通媒体快照刮削未生成完整 NFO/图片")
                    continue
                tmdbid = self._extract_tmdbid(file, mi, dst_backend)
                if tmdbid and not force_nfo:
                    log.info(f"[Scraper]读取到本地nfo文件的tmdbid：{tmdbid}")
                    if self._metadata_gateway is None:
                        log.warn(f"[Scraper]{file} 元数据网关不可用，legacy TMDB 兜底失败")
                        continue
                    mi.set_provider_data(
                        self._metadata_gateway.details("tmdb", tmdbid, media_type=mi.type, append_to_response="all")
                    )
                    media_info = mi
                else:
                    # 尝试从下载历史中读取订阅时记录的 TMDB 信息（TMDB 身份确定，季/集仍从文件名解析）
                    (
                        dl_tmdbid,
                        dl_type,
                        dl_anchor_provider,
                        dl_anchor_external,
                        dl_content_profile,
                    ) = self._download_history_tmdb(file)
                    if dl_tmdbid or dl_anchor_provider:
                        log.info(f"[Scraper]从下载历史读取到tmdbid：{dl_tmdbid}，类型={dl_type}")
                        dl_mtype = ProviderMediaType.from_value(dl_type) or mi.type or ProviderMediaType.MOVIE
                        db_anchor = str(dl_tmdbid or "").startswith("DB:") or (
                            dl_anchor_provider and dl_anchor_provider != "tmdb" and not str(dl_tmdbid or "").isdigit()
                        )
                        if db_anchor:
                            # 豆瓣直连：不查询 TMDB，季/集只从文件名解析
                            media_info = mi
                            media_info.tmdb_id = str(dl_tmdbid) if str(dl_tmdbid or "").startswith("DB:") else ""
                            media_info.douban_id = str(dl_anchor_external or "").strip() or (
                                str(dl_tmdbid)[3:] if str(dl_tmdbid or "").startswith("DB:") else ""
                            )
                            media_info.type = dl_mtype
                            log.info(f"[Scraper]豆瓣订阅刮削使用豆瓣元数据：{dl_anchor_external}")
                        else:
                            if self._metadata_gateway is None:
                                log.warn(f"[Scraper]{file} 元数据网关不可用，legacy TMDB 兜底失败")
                                media_info = mi
                            else:
                                tmdb_details = self._metadata_gateway.details(
                                    "tmdb", dl_tmdbid, media_type=dl_mtype, append_to_response="all"
                                )
                                if tmdb_details:
                                    mi.set_provider_data(tmdb_details)
                                    # 再用 identify_files 解析季/集（有 tmdb_info 时跳过网络查询，仅做本地解析）
                                    medias = self._metadata_gateway.media_info_on_files(
                                        file_list=[file],
                                        tmdb_info=tmdb_details,
                                        media_type=dl_mtype,
                                        append_to_response="all",
                                        backend=dst_backend,
                                    )
                                    if medias:
                                        media_info = next(iter(medias.values()), mi)
                                    else:
                                        media_info = mi
                                else:
                                    log.warn(f"[Scraper]{file} 网关未返回下载历史 TMDB 详情，保留本地识别结果")
                                    media_info = mi
                        media_info.anchor_provider = dl_anchor_provider or media_info.anchor_provider
                        media_info.anchor_external_id = dl_anchor_external or media_info.anchor_external_id
                        media_info.content_profile = dl_content_profile or media_info.content_profile or "default"
                    else:
                        if self._metadata_gateway is None:
                            log.warn(f"[Scraper]{file} 元数据网关不可用，无法识别媒体信息")
                            continue
                        medias = self._metadata_gateway.media_info_on_files(
                            file_list=[file], append_to_response="all", backend=dst_backend
                        )
                        if not medias:
                            log.warn(f"[Scraper]{file} 无法识别媒体信息")
                            continue
                        media_info = next(iter(medias.values()), None)
                if media_info is not None and self._metadata_gateway is not None:
                    # 转移阶段已写入的快照优先直接读取，避免重复抓取和重复限流。
                    snapshot = self._latest_snapshot(media_info)
                    if snapshot is None:
                        snapshot = self._compose(media_info, with_episodes=True, persist=True)
                    if snapshot is not None:
                        scraped = self.gen_snapshot_files(
                            snapshot=snapshot,
                            media=media_info,
                            dir_path=os.path.dirname(file),
                            file_name=os.path.splitext(os.path.basename(file))[0],
                            file_ext=os.path.splitext(file)[-1],
                            force_nfo=force_nfo,
                            force_pic=force_pic,
                            dst_backend=dst_backend,
                        )
                        if scraped:
                            log.info(f"[Scraper]{file} 快照刮削完成")
                        else:
                            log.error(f"[Scraper]{file} 快照刮削未生成完整 NFO/图片")
                        continue
                    log.warn(f"[Scraper]{file} 无法合成元数据快照")
                if not self._legacy_tmdb_fallback:
                    log.warn(f"[Scraper]{file} legacy TMDB 回退已禁用，跳过")
                    continue
                if not media_info or not media_info.provider_data:
                    log.warn(f"[Scraper]{file} 无法获取TMDB信息")
                    continue
                self.gen_scraper_files(
                    media=media_info,
                    dir_path=os.path.dirname(file),
                    file_name=os.path.splitext(os.path.basename(file))[0],
                    file_ext=os.path.splitext(file)[-1],
                    force=True,
                    force_nfo=force_nfo,
                    force_pic=force_pic,
                    dst_backend=dst_backend,
                )
                log.info(f"[Scraper]{file} 刮削完成")
        except Exception as e:
            log.error(f"[Scraper]刮削异常：{e}")
            ExceptionUtils.exception_traceback(e)

    def gen_snapshot_files(
        self, snapshot, media, dir_path, file_name, file_ext, force_nfo=False, force_pic=False, dst_backend=None
    ):
        """无 TMDB 场景：直接消费 MediaMetadata 快照生成 NFO/图片."""
        self._init_config()
        if not self._scraper_nfo and not self._scraper_pic:
            log.warn("[Scraper]刮削配置为空，跳过快照刮削")
            return False
        self._local.dst_backend = dst_backend
        self._downloader.set_dst_backend(dst_backend)
        if not getattr(snapshot, "content_profile", "") and getattr(media, "content_profile", ""):
            snapshot.content_profile = media.content_profile
        if not force_nfo and self._nfo_needs_rewrite(dir_path, file_name, media.type):
            log.info(f"[Scraper]{file_name} 现有 NFO 不完整，强制重写")
            force_nfo = True
        if media.type == ProviderMediaType.MOVIE:
            self._scrape_movie_from_snapshot(snapshot, media, dir_path, file_name, force_nfo, force_pic)
        else:
            self._scrape_tv_from_snapshot(snapshot, media, dir_path, file_name, file_ext, force_nfo, force_pic)
        target = os.path.join(dir_path, f"{file_name}{file_ext}")
        return self._has_scraped_metadata(target, dst_backend)

    def _scrape_movie_from_snapshot(self, snapshot, media, dir_path, file_name, force_nfo, force_pic):
        scraper_movie_nfo = self._scraper_nfo.get("movie", {})
        scraper_movie_pic = self._scraper_pic.get("movie", {})
        # 先运行插件快照处理器，再补图/补演员，避免 actor_fallback 尚未生成。
        scraper_processor_registry.enrich_snapshot(snapshot)
        self._ensure_snapshot_images(snapshot)
        # 图片落盘并裁剪后再写 NFO，确保 poster/thumb 标签指向真实存在的文件。
        self._download_snapshot_images(snapshot, dir_path, scraper_movie_pic, force_pic)
        self._normalize_snapshot_poster(snapshot, dir_path)
        self._prune_missing_image_assets(snapshot, dir_path)
        if scraper_movie_nfo.get("basic") or scraper_movie_nfo.get("credits"):
            nfo_path = os.path.join(dir_path, f"{file_name}.nfo")
            if force_nfo or not self._exists(nfo_path):
                fallback_title = (
                    self._download_history_title(os.path.join(dir_path, file_name))
                    or str(getattr(media, "title", "") or "")
                    or file_name
                )
                self._nfo_gen.gen_movie_nfo_from_snapshot(
                    snapshot, scraper_movie_nfo, dir_path, file_name, fallback_title=fallback_title
                )
        self._cleanup_stale_nfos(dir_path, file_name)
        if getattr(self._local, "dst_backend", None) is None:
            self._apply_watermark(snapshot, dir_path)
        self._ensure_poster_thumb(dir_path, file_name)

    def _ensure_poster_thumb(self, dir_path: str, file_name: str) -> None:
        """Emby 首页缩略图优先使用 poster，避免回退到未裁剪的 fanart."""
        poster_path = ""
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = os.path.join(dir_path, f"poster{ext}")
            if os.path.exists(candidate):
                poster_path = candidate
                break
        if not poster_path:
            return
        thumb_path = os.path.join(dir_path, "thumb.jpg")
        try:
            if not os.path.exists(thumb_path):
                shutil.copyfile(poster_path, thumb_path)
            nfo_path = os.path.join(dir_path, f"{file_name}.nfo")
            if os.path.exists(nfo_path):
                with open(nfo_path, encoding="utf-8", errors="ignore") as handle:
                    content = handle.read()
                content = re.sub(r"<thumb>.*?</thumb>", "<thumb>thumb.jpg</thumb>", content, flags=re.S)
                with open(nfo_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
        except Exception as exc:  # noqa: BLE001 - 缩略图失败不影响主海报
            log.debug(f"[Scraper]生成 poster thumb 失败: {exc}")

    def _scrape_tv_from_snapshot(self, snapshot, media, dir_path, file_name, file_ext, force_nfo, force_pic):
        scraper_tv_nfo = self._scraper_nfo.get("tv", {})
        scraper_tv_pic = self._scraper_pic.get("tv", {})
        self._ensure_snapshot_images(snapshot)
        season_dir = bool(
            re.match(
                r"^(?:Season|S)\s*\d+$",
                os.path.basename(dir_path.rstrip("/\\")),
                re.IGNORECASE,
            )
        )
        tv_root = os.path.dirname(dir_path) if season_dir else dir_path
        season_number = int(media.get_season_seq() or 1)
        episode_number = int(media.get_episode_seq() or 1)

        if scraper_tv_nfo.get("basic") or scraper_tv_nfo.get("credits"):
            tv_nfo = os.path.join(tv_root, "tvshow.nfo")
            if force_nfo or not self._exists(tv_nfo):
                self._nfo_gen.gen_tv_nfo_from_snapshot(
                    snapshot,
                    scraper_tv_nfo,
                    tv_root,
                    show_title=str(getattr(media, "title", "") or ""),
                )

        season = next((item for item in snapshot.seasons if item.season_number == season_number), None)
        if season is not None and scraper_tv_nfo.get("season_basic"):
            season_nfo = os.path.join(dir_path, "season.nfo")
            if force_nfo or not self._exists(season_nfo):
                self._nfo_gen.gen_season_nfo_from_snapshot(season, season_number, dir_path)

        episode = next(
            (
                item
                for item in snapshot.episodes
                if item.season_number == season_number and item.episode_number == episode_number
            ),
            None,
        )
        if episode is not None and (scraper_tv_nfo.get("episode_basic") or scraper_tv_nfo.get("episode_credits")):
            episode_nfo = os.path.join(dir_path, f"{file_name}.nfo")
            if force_nfo or not self._exists(episode_nfo):
                self._nfo_gen.gen_episode_nfo_from_snapshot(
                    snapshot, episode, scraper_tv_nfo, season_number, dir_path, file_name
                )

        self._download_snapshot_images(snapshot, tv_root, scraper_tv_pic, force_pic)
        self._ensure_poster_file(tv_root)
        if season is not None and scraper_tv_pic.get("season_poster") and season.poster:
            self._downloader.download(
                season.poster,
                dir_path,
                "season{}-poster".format(str(season_number).rjust(2, "0")),
                force_pic,
            )
        if episode is not None and scraper_tv_pic.get("episode_thumb") and episode.still:
            self._downloader.download(episode.still, dir_path, f"{file_name}-thumb", force_pic)
        self._download_snapshot_season_images(
            snapshot, media, season, season_number, tv_root, scraper_tv_pic, force_pic
        )

    def _apply_watermark(self, snapshot, target_dir):
        if getattr(self._local, "dst_backend", None) is not None:
            return
        scraper_processor_registry.process_watermark(target_dir, snapshot)

    @staticmethod
    def _find_image(target_dir: str, name: str) -> str | None:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = os.path.join(target_dir, f"{name}{ext}")
            if os.path.exists(candidate):
                return candidate
        return None

    def _cleanup_stale_nfos(self, target_dir: str, current_file_name: str) -> None:
        """删除同番号的旧 NFO（如 DV-1622-破解-C.nfo），避免 Emby 读到旧元数据."""
        try:
            names = os.listdir(target_dir)
        except OSError:
            return
        video_ext = (".mp4", ".mkv", ".avi", ".wmv", ".ts", ".m2ts", ".mov")
        video_bases = {os.path.splitext(name)[0] for name in names if name.lower().endswith(video_ext)}
        video_bases.add(current_file_name)
        keep = video_bases | {"tvshow", "season", "movie", "album", "musicvideo"}

        def code_prefix(value: str) -> str:
            match = re.match(r"^([A-Za-z]{2,10})[-_ ]?(\d{2,6})", value)
            return f"{match.group(1)}-{match.group(2)}".upper() if match else ""

        video_prefixes = {code_prefix(base) for base in video_bases if code_prefix(base)}
        for name in names:
            if not name.lower().endswith(".nfo"):
                continue
            stem = name[:-4]
            if stem in keep:
                continue
            prefix = code_prefix(stem)
            if prefix and prefix in video_prefixes:
                path = os.path.join(target_dir, name)
                try:
                    os.remove(path)
                    log.warn(f"[Scraper]删除同番号旧 NFO：{path}")
                except OSError as exc:
                    log.warn(f"[Scraper]删除旧 NFO 失败 {path}: {exc}")

    def _prune_missing_image_assets(self, snapshot, target_dir: str) -> None:
        """NFO 只引用实际存在的图片，避免生成 poster.jpg 悬空标签."""
        images = getattr(snapshot, "images", None)
        if not isinstance(images, dict):
            return
        if not self._find_image(target_dir, "poster"):
            images.pop("poster", None)
        if not self._find_image(target_dir, "fanart"):
            images.pop("fanart", None)
        if not self._find_image(target_dir, "background"):
            images.pop("background", None)

    def _ensure_poster_file(self, target_dir: str) -> str | None:
        """仅允许竖版图兜底；横版剧照/封套绝不能当海报."""
        poster = self._find_image(target_dir, "poster")
        if poster:
            return poster
        for name in ("fanart", "backdrop", "thumb"):
            source = self._find_image(target_dir, name)
            if not source or self._is_placeholder_image(source):
                continue
            try:
                with Image.open(source) as img:
                    if img.width > img.height * 1.05:
                        continue
            except Exception:
                continue
            poster = os.path.join(target_dir, "poster.jpg")
            try:
                shutil.copyfile(source, poster)
            except OSError as exc:
                log.warn(f"[Scraper]海报兜底复制失败 {source}: {exc}")
                return None
            log.warn(f"[Scraper]缺少海报，已用竖版 {name} 兜底生成 poster.jpg")
            return poster
        return None

    def _normalize_snapshot_poster(self, snapshot, target_dir):
        """海报只保留竖版正面封面；横版整张封套/剧照转为 fanart 后删除 poster."""
        if getattr(self._local, "dst_backend", None) is not None:
            return
        poster_path = None
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = os.path.join(target_dir, f"poster{ext}")
            if os.path.exists(candidate):
                poster_path = candidate
                break
        if not poster_path:
            return
        if self._is_placeholder_image(poster_path):
            try:
                os.remove(poster_path)
            except OSError:
                pass
            log.warn(f"[Scraper]删除 NOW PRINTING 占位海报：{poster_path}")
            return
        try:
            with Image.open(poster_path) as img:
                width, height = img.size
                if width > height * 1.15:
                    # 横版整张封套：先保留完整图做 fanart，再只裁正面封面。
                    fanart_path = os.path.join(target_dir, "fanart.jpg")
                    if not os.path.exists(fanart_path):
                        img.save(fanart_path, quality=92)
                    modes = scraper_processor_registry.process_poster(poster_path, snapshot)
                    with Image.open(poster_path) as cropped:
                        cw, ch = cropped.size
                        if cw > ch * 1.15:
                            target_w = max(1, int(ch * 0.71))
                            cropped.crop((max(0, cw - target_w), 0, cw, ch)).save(poster_path, quality=94)
                            modes = list(modes) + ["fallback-right"]
                    log.info(f"[Scraper]封面裁剪模式 {','.join(modes) or 'fallback-right'}：{poster_path}")
                    return
            modes = scraper_processor_registry.process_poster(poster_path, snapshot)
            if modes:
                log.info(f"[Scraper]封面裁剪模式 {','.join(modes)}：{poster_path}")
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Scraper]封面后处理失败 {poster_path}: {exc}")

    @staticmethod
    def _is_placeholder_image(path: str) -> bool:
        """识别 NOW PRINTING 等近灰白占位图，避免写入海报墙."""
        return _poster_is_placeholder(path)

    def _portrait_image_exists(self, target_dir, file_name, min_width=300) -> bool:
        """已有合格竖版图时禁止 force 重下覆盖，防止横版/错误候选破坏海报."""
        if file_name == "poster":
            synthetic = synthetic_poster_path(target_dir)
            if synthetic:
                try:
                    os.remove(synthetic)
                except OSError:
                    pass
                log.warn(f"[Scraper]删除横版剧照裁出的伪海报：{synthetic}")
                return False
            if has_legacy_watermark_marker(target_dir):
                # 旧版 40 字节 marker 说明 poster 来自旧版横版裁切，必须重建。
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    old = os.path.join(target_dir, f"poster{ext}")
                    if os.path.exists(old):
                        try:
                            os.remove(old)
                        except OSError:
                            pass
                # 旧 marker 必须一起清掉，否则海报重建后仍会被判定为旧版。
                try:
                    os.remove(os.path.join(target_dir, ".watermark"))
                except OSError:
                    pass
                log.warn(f"[Scraper]旧版水印标记，重建 poster：{target_dir}")
                return False
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            path = os.path.join(target_dir, f"{file_name}{ext}")
            if not os.path.exists(path):
                continue
            try:
                with Image.open(path) as img:
                    width, height = img.size
                if self._is_placeholder_image(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    return False
                # 只有 >=300px 的竖版才视为已完成；147x200 缩略图仍可暂时保留，
                # 但会继续尝试高清整张封套裁剪。
                return height > width * 1.05 and width >= 300
            except Exception:
                return False
        return False

    def _valid_image(self, target_dir, file_name, min_width, min_height):
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            path = os.path.join(target_dir, f"{file_name}{ext}")
            if not os.path.exists(path):
                continue
            try:
                with Image.open(path) as img:
                    width, height = img.size
                if width >= min_width and height >= min_height:
                    return not self._is_placeholder_image(path)
            except Exception as exc:  # noqa: BLE001 - 损坏图片视为无效
                log.debug(f"[Scraper]图片校验失败 {path}: {exc}")
            try:
                os.remove(path)
            except OSError:
                pass
        return False

    def _download_candidates(
        self,
        candidates,
        target_dir,
        file_name,
        force,
        min_width,
        min_height,
        require_portrait=False,
    ):
        if file_name == "poster" and self._portrait_image_exists(target_dir, "poster", min_width):
            log.debug(f"[Scraper]保留已有竖版海报：{target_dir}")
            return True
        # 海报按优先级依次尝试更多来源；前几个可能是 NOW PRINTING 占位图。
        limit = 12 if file_name == "poster" else 5
        for raw_url in list(candidates)[:limit]:
            url = unwrap_display_image_url(str(raw_url or ""))
            if not url or url.rstrip("/").endswith("/login"):
                continue
            try:
                if not self._downloader.download(url, target_dir, file_name, force):
                    continue
                if self._valid_image(target_dir, file_name, min_width, min_height):
                    if require_portrait:
                        path = next(
                            (
                                os.path.join(target_dir, f"{file_name}{ext}")
                                for ext in (".jpg", ".jpeg", ".png", ".webp")
                                if os.path.exists(os.path.join(target_dir, f"{file_name}{ext}"))
                            ),
                            "",
                        )
                        if path:
                            try:
                                with Image.open(path) as img:
                                    if img.height <= img.width:
                                        os.remove(path)
                                        continue
                            except Exception:  # noqa: BLE001 - 损坏图片继续尝试
                                os.remove(path)
                                continue
                    return True
            except Exception as exc:  # noqa: BLE001 - 候选 fallback
                log.warn(f"[Scraper]图片候选下载失败 {file_name}: {url}: {exc}")
        log.warn(f"[Scraper]图片下载失败，候选为空: {file_name}")
        return False

    @staticmethod
    def _snapshot_has_content(snapshot) -> bool:
        """快照至少要有标题，否则生成的 NFO 为空，应重新合成."""
        fields = getattr(snapshot, "fields", None) or {}
        title = getattr(fields.get("title"), "value", None) if hasattr(fields, "get") else None
        return bool(title)

    @staticmethod
    def _image_assets(assets) -> list[ImageAsset]:
        result: list[ImageAsset] = []
        for item in assets or []:
            if isinstance(item, ImageAsset):
                result.append(item)
            elif isinstance(item, dict):
                result.append(ImageAsset(**item))
        return result

    def _ensure_snapshot_images(self, snapshot) -> None:
        """用快照主来源补齐图片/演职人员，优先复用聚合 provider 的合并结果."""
        if self._metadata_gateway is None:
            return
        images = getattr(snapshot, "images", None)
        if not isinstance(images, dict):
            images = {}
            snapshot.images = images
        need_images = not any(images.values())
        # 聚合来源可能只返回截图（fanart），不能因此跳过海报回补。
        need_poster = not images.get("poster")
        need_credits = not getattr(snapshot, "credits", None)
        if not need_images and not need_poster and not need_credits:
            return
        extra = getattr(snapshot, "extra", {}) or {}
        preferred = [
            str(getattr(snapshot, "primary_provider", "") or "").strip(),
            str(extra.get("source_provider") or "").strip(),
        ]
        refs = list(getattr(snapshot, "refs", []) or [])
        ordered = []
        for provider in preferred:
            if not provider:
                continue
            for ref in refs:
                if str(getattr(ref, "provider", "") or "") == provider and ref not in ordered:
                    ordered.append(ref)
        ordered.extend(ref for ref in refs if ref not in ordered)
        for ref in ordered:
            provider = str(getattr(ref, "provider", "") or "").strip()
            external_id = str(getattr(ref, "external_id", "") or "").strip()
            if not provider or not external_id or provider in {"content_id", "tmdb", "imdb"}:
                continue
            record = self._lookup(
                provider,
                external_id,
                media_type=getattr(ref, "media_type", None),
                content_profile=getattr(snapshot, "content_profile", None),
                allow_private=True,
            )
            if not record:
                continue
            record_images = record.get("images") or {}
            if need_poster:
                posters = self._image_assets(record_images.get("poster"))
                if posters:
                    snapshot.images["poster"] = posters
                    need_poster = False
            if need_images:
                for kind, assets in record_images.items():
                    if snapshot.images.get(kind) or not isinstance(assets, list) or not assets:
                        continue
                    snapshot.images[kind] = self._image_assets(assets)
                need_images = not any(snapshot.images.values())
            credits = record.get("credits") or []
            if need_credits and credits:
                snapshot.credits = [Credit(**item) for item in credits]
                need_credits = False
            record_extra = record.get("extra") or {}
            if record_extra:
                snapshot.extra.update(record_extra)
            if not need_images and not need_poster and not need_credits:
                return
        if need_credits:
            # 旧快照可能只有插件写入的演员名字（actor_fallback），没有 credits。
            names = [str(name).strip() for name in (snapshot.extra.get("actor_fallback") or []) if str(name).strip()]
            if names:
                images = snapshot.extra.get("actor_images") or {}
                provider = str(snapshot.primary_provider or snapshot.extra.get("source_provider") or "")
                snapshot.credits = [
                    Credit(
                        name=name,
                        role="actor",
                        order=index,
                        provider=provider,
                        image_url=images.get(name),
                    )
                    for index, name in enumerate(names)
                ]

    def _download_snapshot_images(self, snapshot, target_dir, scraper_pic, force_pic):
        mapping = (("poster", "poster"), ("backdrop", "fanart"), ("logo", "logo"), ("thumb", "thumb"))
        for image_type, file_name in mapping:
            enabled = scraper_pic.get(image_type) or (image_type == "backdrop" and scraper_pic.get("fanart"))
            if not enabled:
                continue
            if image_type == "backdrop":
                candidates = self._images.candidates(snapshot, "fanart") or self._images.candidates(
                    snapshot, "backdrop"
                )
                self._download_candidates(candidates, target_dir, file_name, force_pic, 500, 250)
                continue
            if image_type == "thumb":
                base_candidates = self._images.candidates(snapshot, "thumb")
                if self._download_candidates(base_candidates, target_dir, file_name, force_pic, 300, 150):
                    continue
                fanart_candidates = self._images.candidates(snapshot, "fanart") or self._images.candidates(
                    snapshot, "backdrop"
                )
                self._download_candidates(fanart_candidates, target_dir, file_name, force_pic, 500, 250)
                continue
            candidates = self._images.candidates(snapshot, image_type)
            # JAV 站点真正的竖版正面封面通常只有 147x200（DMM ps / JavBus thumb），
            # 不能因为尺寸小就拒绝，否则只剩 800x538 横版封套，最终被裁成封底/剧照。
            min_width = 120 if image_type == "poster" else 100
            min_height = 160 if image_type == "poster" else 100
            if image_type == "poster":
                # 允许下载 DMM/JavBus 的高清横版整张封套，随后由 poster 处理器
                # 只裁正面封面；不会使用 fanart/剧照兜底。
                self._download_candidates(
                    candidates,
                    target_dir,
                    file_name,
                    force_pic,
                    min_width,
                    min_height,
                )
                continue
            self._download_candidates(
                candidates,
                target_dir,
                file_name,
                force_pic,
                min_width,
                min_height,
            )
        # 额外图片类型：优先使用快照内已有资源（插件可扩展），缺失再由 Fanart.tv 补齐。
        for image_type in ("background", "disc", "banner", "clearart"):
            if not scraper_pic.get(image_type):
                continue
            candidates = self._images.candidates(snapshot, image_type)
            self._download_candidates(candidates, target_dir, image_type, force_pic, 100, 100)
        self._download_fanart_images(snapshot, target_dir, scraper_pic, force_pic)
        if scraper_pic.get("actor"):
            self._download_snapshot_actors(snapshot, target_dir, force_pic)

    def _snapshot_fanart_id(self, snapshot, media=None) -> tuple[ProviderMediaType, str] | None:
        """解析 Fanart.tv 所需 ID：电影用 TMDB，剧集用 TVDB."""
        media_type = getattr(snapshot, "media_type", None)
        if not isinstance(media_type, ProviderMediaType):
            media_type = getattr(media, "type", None)
        if not isinstance(media_type, ProviderMediaType):
            return None
        if media_type == ProviderMediaType.MOVIE:
            if media is not None and getattr(media, "tmdb_id", None):
                return media_type, str(media.tmdb_id)
            refs = getattr(snapshot, "refs", []) or []
            for provider in ("tmdb", "imdb"):
                for ref in refs:
                    if getattr(ref, "provider", "") == provider:
                        return media_type, str(ref.external_id)
            return None
        if media is not None and getattr(media, "tvdb_id", None):
            return media_type, str(media.tvdb_id)
        for ref in getattr(snapshot, "refs", []) or []:
            if getattr(ref, "provider", "") == "tvdb":
                return media_type, str(ref.external_id)
        return None

    def _download_fanart_images(self, snapshot, target_dir, scraper_pic, force_pic) -> None:
        fanart = getattr(self, "fanart", None)
        if fanart is None:
            return
        query = self._snapshot_fanart_id(snapshot)
        if query is None:
            return
        media_type, query_id = query
        specs = [
            ("background", "background", fanart.get_background),
            ("logo", "logo", fanart.get_logo),
            ("banner", "banner", fanart.get_banner),
            ("thumb", "thumb", fanart.get_thumb),
        ]
        if media_type == ProviderMediaType.MOVIE:
            specs.append(("disc", "disc", fanart.get_disc))
        else:
            specs.append(("clearart", "clearart", fanart.get_clearart))
        for image_type, file_name, getter in specs:
            if not scraper_pic.get(image_type):
                continue
            try:
                url = getter(media_type=media_type, queryid=query_id)
                if url:
                    self._downloader.download(url, target_dir, file_name, force_pic)
            except Exception as exc:  # noqa: BLE001
                log.debug(f"[Scraper]Fanart {image_type} 下载失败: {exc}")

    def _download_snapshot_season_images(
        self, snapshot, media, season, season_number, tv_root, scraper_pic, force_pic
    ) -> None:
        fanart = getattr(self, "fanart", None)
        if fanart is None:
            return
        query = self._snapshot_fanart_id(snapshot, media)
        if query is None:
            return
        media_type, query_id = query
        if media_type == ProviderMediaType.MOVIE:
            return
        season_no = int(season_number)
        if scraper_pic.get("season_poster") and (season is None or not season.poster):
            url = fanart.get_seasonposter(media_type=media_type, queryid=query_id, season=season_no)
            if url:
                self._downloader.download(
                    url,
                    tv_root,
                    "season{}-poster".format(str(season_no).rjust(2, "0")),
                    force_pic,
                )
        if scraper_pic.get("season_banner"):
            url = fanart.get_seasonbanner(media_type=media_type, queryid=query_id, season=season_no)
            if url:
                self._downloader.download(
                    url,
                    tv_root,
                    "season{}-banner".format(str(season_no).rjust(2, "0")),
                    force_pic,
                )
        if scraper_pic.get("season_thumb"):
            url = fanart.get_seasonthumb(media_type=media_type, queryid=query_id, season=season_no)
            if url:
                self._downloader.download(
                    url,
                    tv_root,
                    "season{}-landscape".format(str(season_no).rjust(2, "0")),
                    force_pic,
                )

    def _download_snapshot_actors(self, snapshot, target_dir, force_pic):
        actors = self._images.actor_candidates(snapshot)
        if not actors or getattr(self._local, "dst_backend", None) is not None:
            return
        actors_dir = os.path.join(target_dir, "actors")
        os.makedirs(actors_dir, exist_ok=True)
        for name, url in actors:
            safe_name = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()
            if not safe_name:
                continue
            try:
                self._downloader.download(url, actors_dir, safe_name, force_pic)
            except Exception as exc:  # noqa: BLE001
                log.debug(f"[Scraper]演员图片下载失败 {name}: {exc}")

    def _compose_standard_snapshot(self, file_path: str, media_info):
        """普通媒体接入 metadata snapshot：优先历史/NFO 锚点，其次按默认策略搜索."""
        if self._metadata_gateway is None:
            return None
        provider = ""
        external_id = ""
        history = self._download_history_tmdb(file_path)
        dl_tmdbid, dl_type, dl_provider, dl_external, _dl_profile = history
        if dl_provider and dl_external:
            provider, external_id = str(dl_provider), str(dl_external)
        elif dl_tmdbid:
            raw = str(dl_tmdbid)
            if raw.startswith("DB:"):
                provider, external_id = "douban", raw[3:]
            elif raw.isdigit():
                provider, external_id = "tmdb", raw
        media_type = getattr(media_info, "type", None) or ProviderMediaType.MOVIE
        policy = str((settings.get("media") or {}).get("metadata_default_policy") or "tmdb_primary")
        if self._metadata_gateway is not None and not provider:
            # 下载历史/订阅已经给出明确锚点时，不能被标题识别覆盖。
            self._identify_anchor(media_info, policy=policy)
        anchor_provider = str(getattr(media_info, "anchor_provider", "") or "")
        anchor_external = str(getattr(media_info, "anchor_external_id", "") or "")
        if anchor_provider and anchor_external:
            provider, external_id = anchor_provider, anchor_external
        if not provider:
            tmdbid = getattr(media_info, "tmdb_id", None)
            if tmdbid:
                provider, external_id = "tmdb", str(tmdbid)
            elif getattr(media_info, "douban_id", None):
                provider, external_id = "douban", str(media_info.douban_id)
        if not provider:
            primary = policy.split("_", 1)[0]
            if primary not in {"tmdb", "douban", "bangumi"}:
                primary = "tmdb"
            title = str(getattr(media_info, "title", "") or "")
            if title:
                try:
                    hits = self._search(
                        query=title,
                        provider=primary,
                        media_type=media_type,
                        content_profile="anime" if primary == "bangumi" else "default",
                        limit=5,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warn(f"[Scraper]普通媒体快照搜索失败: {exc}")
                    hits = []
                hit = next(
                    (item for item in hits if str(item.get("title") or "").strip() == title.strip()),
                    hits[0] if hits else None,
                )
                if hit:
                    ref = hit.get("ref") or {}
                    provider = str(ref.get("provider") or "")
                    external_id = str(ref.get("external_id") or "")
                    parsed_type = ProviderMediaType.from_value(str(hit.get("media_type") or ""))
                    if parsed_type != ProviderMediaType.UNKNOWN:
                        media_type = parsed_type
        if not provider or not external_id:
            return None
        if provider == "bangumi":
            media_info.type = ProviderMediaType.ANIME
            media_info.content_profile = "anime"
        try:
            return self._compose(
                media_info,
                policy=policy,
                anchor_provider=provider,
                content_profile="anime" if provider == "bangumi" else None,
                with_episodes=True,
                persist=True,
            )
        except Exception as exc:  # noqa: BLE001 - 快照失败继续旧路径
            log.warn(f"[Scraper]普通媒体快照合成失败: {exc}")
            return None

    def _download_history_title(self, file_path: str) -> str:
        """从下载历史读取任务标题，供缺少元数据的 NFO 回退."""
        try:
            repo = DownloadHistoryRepositoryAdapter()
            base = os.path.splitext(os.path.basename(file_path))[0]
            candidates = [base, re.sub(r"[-_](?:C|HD|4K|UHD|CD\d+)$", "", base, flags=re.I)]
            for code in dict.fromkeys(candidates):
                rows = repo.get_by_identity(anchor_provider="content_id", anchor_external_id=code)
                for row in rows or []:
                    title = str(getattr(row, "TITLE", "") or getattr(row, "title", "") or "").strip()
                    if title:
                        return title
            history = repo.get_download_history_by_path(file_path)
            if not history:
                parent = os.path.dirname(file_path)
                if parent and parent != file_path:
                    history = repo.get_download_history_by_path(parent)
            if history:
                return str(getattr(history, "TITLE", "") or "").strip()
        except Exception as exc:  # noqa: BLE001 - 历史不可用不阻断刮削
            log.debug(f"[Scraper]读取下载历史标题失败 {file_path}: {exc}")
        return ""

    def _download_history_tmdb(self, file_path):
        """从下载历史中读取订阅时记录的 TMDB 信息。

        匹配方式：下载历史的 SAVE_PATH 是文件/目录所在路径。
        返回 (tmdbid: int, media_type: str)，未匹配时返回 (None, "")。
        """
        try:
            repo = DownloadHistoryRepositoryAdapter()
            history = repo.get_download_history_by_path(file_path)
            if not history:
                parent = os.path.dirname(file_path)
                if parent and parent != file_path:
                    history = repo.get_download_history_by_path(parent)
            log.debug(f"[Scraper]下载历史查询: {os.path.normpath(file_path)} -> {bool(history)}")
            if history:
                # get_download_history_by_path 返回原始 ORM 对象，字段为大写
                tmdbid = getattr(history, "TMDBID", "") or ""
                mtype = getattr(history, "TYPE", "") or ""
                anchor_provider = getattr(history, "ANCHOR_PROVIDER", None)
                anchor_external = getattr(history, "ANCHOR_EXTERNAL_ID", None)
                if str(tmdbid).startswith("DB:") or str(tmdbid).isdigit() or anchor_provider:
                    return (
                        str(tmdbid)
                        if str(tmdbid).startswith("DB:")
                        else (int(tmdbid) if str(tmdbid).isdigit() else None),
                        mtype,
                        anchor_provider,
                        anchor_external,
                        getattr(history, "CONTENT_PROFILE", None),
                    )
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Scraper]读取下载历史 TMDB 失败: {file_path} - {e}")
        return None, "", None, None, None

    def _extract_tmdbid(self, file_path, meta_info, dst_backend=None):
        """从本地 NFO 文件提取 TMDB ID"""
        if meta_info.type == ProviderMediaType.MOVIE:
            movie_nfo = os.path.join(os.path.dirname(file_path), "movie.nfo")
            if dst_backend is not None:
                if dst_backend.exists(movie_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo_remote(movie_nfo, dst_backend)
                file_nfo = os.path.join(os.path.splitext(file_path)[0] + ".nfo")
                if dst_backend.exists(file_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo_remote(file_nfo, dst_backend)
            else:
                if os.path.exists(movie_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo(movie_nfo)
                file_nfo = os.path.join(os.path.splitext(file_path)[0] + ".nfo")
                if os.path.exists(file_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo(file_nfo)
        else:
            tv_nfo = os.path.join(os.path.dirname(os.path.dirname(file_path)), "tvshow.nfo")
            if dst_backend is not None:
                if dst_backend.exists(tv_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo_remote(tv_nfo, dst_backend)
            else:
                if os.path.exists(tv_nfo):
                    return MediaLibrary.get_tmdbid_from_nfo(tv_nfo)
        return None

    def _exists(self, path: str) -> bool:
        """后端感知的存在性检查（远程目标用 dst_backend.exists）"""
        backend = getattr(self._local, "dst_backend", None)
        if backend is not None:
            try:
                return bool(backend.exists(path))
            except Exception:  # noqa: BLE001
                return False
        return os.path.exists(path)

    def gen_scraper_files(
        self, media, dir_path, file_name, file_ext, force=False, force_nfo=False, force_pic=False, dst_backend=None
    ):
        """刮削元数据入口"""
        # 单例在启动时只加载一次配置，这里每次刮削前重新读取，保证运行期配置变更生效
        self._init_config()
        if not force and not self._scraper_flag:
            log.warn("[Scraper]刮削标志未启用，跳过")
            return False
        if not self._scraper_nfo and not self._scraper_pic:
            log.warn("[Scraper]刮削配置为空，跳过")
            return False
        self._scraper_nfo = self._scraper_nfo or {}
        self._scraper_pic = self._scraper_pic or {}
        self._local.dst_backend = dst_backend
        if not force_nfo and self._nfo_needs_rewrite(dir_path, file_name, media.type):
            log.info(f"[Scraper]{file_name} 现有 NFO 不完整，强制重写")
            force_nfo = True
        self._downloader.set_dst_backend(dst_backend)
        log.info(
            f"[Scraper]开始生成刮削文件：dir={dir_path}, file={file_name}, "
            f"type={media.type}, backend={dst_backend is not None}, "
            f"nfo_keys={list(self._scraper_nfo.keys())}, pic_keys={list(self._scraper_pic.keys())}"
        )

        try:
            started = time.perf_counter()
            raw_profile = getattr(media, "content_profile", "")
            profile = raw_profile if isinstance(raw_profile, str) else ""
            snapshot = getattr(media, "snapshot", None)
            if snapshot is not None and not isinstance(snapshot, MediaMetadata):
                snapshot = None
            if snapshot is not None and not self._snapshot_has_content(snapshot):
                log.warn(f"[Scraper]{file_name} 现有快照缺少标题，重新合成")
                snapshot = None
            if snapshot is None and self._metadata_gateway is not None:
                snapshot = self._latest_snapshot(media)
                if not isinstance(snapshot, MediaMetadata) or not self._snapshot_has_content(snapshot):
                    snapshot = None
            if snapshot is None and profile not in ("", "default") and self._metadata_gateway is not None:
                # 转移阶段已持久化快照；这里只对旧记录补一次，并复用近期快照。
                snapshot = self._compose(
                    media,
                    with_episodes=True,
                    persist=True,
                    max_age_seconds=1800,
                )
                if not isinstance(snapshot, MediaMetadata):
                    snapshot = None
            if snapshot is not None:
                ok = self.gen_snapshot_files(
                    snapshot=snapshot,
                    media=media,
                    dir_path=dir_path,
                    file_name=file_name,
                    file_ext=file_ext,
                    force_nfo=force_nfo,
                    force_pic=force_pic,
                    dst_backend=dst_backend,
                )
                if ok:
                    log.info(f"[Scraper]{file_name} 快照刮削完成（复用转移快照，{time.perf_counter() - started:.2f}s）")
                else:
                    log.error(f"[Scraper]{file_name} 快照刮削未生成完整 NFO/图片")
                return ok
            if media.type == ProviderMediaType.MOVIE:
                self._scrape_movie(media, dir_path, file_name, force_nfo, force_pic)
            else:
                self._scrape_tv(media, dir_path, file_name, file_ext, force_nfo, force_pic)
            target = os.path.join(dir_path, f"{file_name}{file_ext}")
            ok = self._has_scraped_metadata(target, dst_backend)
            if ok:
                log.info(f"[Scraper]刮削文件生成完成：{file_name}")
            else:
                log.error(f"[Scraper]刮削文件生成不完整：{file_name}")
            return ok
        except Exception as e:
            log.error(f"[Scraper]刮削文件生成失败：{file_name}，错误：{e}")
            ExceptionUtils.exception_traceback(e)
            return False

    def _scrape_movie(self, media, dir_path, file_name, force_nfo, force_pic):
        """刮削电影元数据 — 各步骤独立容错，单步失败不影响其他刮削输出."""
        scraper_movie_nfo = self._scraper_nfo.get("movie", {})
        scraper_movie_pic = self._scraper_pic.get("movie", {})
        tmdbinfo = dict(media.provider_data or {}) if isinstance(media.provider_data, dict) else {}
        # 聚合元数据为空时仍写入已识别的标题/年份，避免生成空 title 的 NFO。
        if not tmdbinfo.get("title"):
            tmdbinfo["title"] = (
                self._download_history_title(os.path.join(dir_path, file_name))
                or media.title
                or media.get_title_string()
            )
        if not tmdbinfo.get("original_title"):
            tmdbinfo["original_title"] = media.original_title or media.title or ""
        if not tmdbinfo.get("release_date"):
            tmdbinfo["release_date"] = str(media.year or "")

        if scraper_movie_nfo.get("basic") or scraper_movie_nfo.get("credits"):
            nfo_exists = self._exists(os.path.join(dir_path, "movie.nfo")) or self._exists(
                os.path.join(dir_path, f"{file_name}.nfo")
            )
            if force_nfo or not nfo_exists:
                try:
                    doubaninfo = self._fetch_douban(media, scraper_movie_nfo)
                    credits_info = media.provider_data or tmdbinfo
                    directors, actors = self._fetch_credits(credits_info, scraper_movie_nfo, doubaninfo)
                    self._nfo_gen.gen_movie_nfo(tmdbinfo, directors, actors, scraper_movie_nfo, dir_path, file_name)
                except Exception as e:
                    log.error(f"[Scraper]生成 movie.nfo 失败：{e}")

        try:
            self._download_images(media, dir_path, scraper_movie_pic, force_pic)
            # 普通 TMDB 路径也可能拿到横版图，写入后统一做竖版裁切。
            self._normalize_snapshot_poster(None, dir_path)
        except Exception as e:
            log.error(f"[Scraper]下载电影图片失败：{e}")

    def _scrape_tv(self, media, dir_path, file_name, file_ext, force_nfo, force_pic):
        """刮削电视剧元数据 — 各步骤独立容错，单步失败不影响其他刮削输出."""
        scraper_tv_nfo = self._scraper_nfo.get("tv", {})
        scraper_tv_pic = self._scraper_pic.get("tv", {})
        season_dir = bool(
            re.match(
                r"^(?:Season|S)\s*\d+$",
                os.path.basename(dir_path.rstrip("/\\")),
                re.IGNORECASE,
            )
        )
        tv_root = os.path.dirname(dir_path) if season_dir else dir_path

        # ---- tvshow.nfo ----
        if force_nfo or not self._exists(os.path.join(tv_root, "tvshow.nfo")):
            if scraper_tv_nfo.get("basic") or scraper_tv_nfo.get("credits"):
                try:
                    doubaninfo = self._fetch_douban(media, scraper_tv_nfo)
                    directors, actors = self._fetch_credits(media.provider_data, scraper_tv_nfo, doubaninfo)
                    self._nfo_gen.gen_tv_nfo(media.provider_data, directors, actors, scraper_tv_nfo, tv_root)
                except Exception as e:
                    log.error(f"[Scraper]生成 tvshow.nfo 失败：{e}")

        # ---- tv 图片 ----
        try:
            self._download_tv_images(media, tv_root, scraper_tv_pic, force_pic)
        except Exception as e:
            log.error(f"[Scraper]下载 TV 图片失败：{e}")

        # ---- 季/集详情 ----
        need_season_detail = (
            scraper_tv_nfo.get("season_basic")
            or scraper_tv_nfo.get("episode_basic")
            or scraper_tv_nfo.get("episode_credits")
            or scraper_tv_pic.get("season_poster")
        )
        seasoninfo = None
        if need_season_detail and str(getattr(media, "tmdb_id", "") or "").isdigit():
            if self._metadata_gateway is None:
                log.warn("[Scraper]元数据网关不可用，跳过季详情")
            else:
                try:
                    seasoninfo = self._metadata_gateway.season_episodes(
                        "tmdb", media.tmdb_id, int(media.get_season_seq())
                    )
                except Exception as e:
                    log.error(f"[Scraper]获取季详情失败：{e}")

        # ---- season.nfo ----
        if scraper_tv_nfo.get("season_basic"):
            if force_nfo or not self._exists(os.path.join(dir_path, "season.nfo")):
                if seasoninfo:
                    try:
                        self._nfo_gen.gen_season_nfo(seasoninfo, int(media.get_season_seq()), dir_path)
                    except Exception as e:
                        log.error(f"[Scraper]生成 season.nfo 失败：{e}")

        # ---- episode.nfo ----
        if scraper_tv_nfo.get("episode_basic") or scraper_tv_nfo.get("episode_credits"):
            if force_nfo or not self._exists(os.path.join(dir_path, f"{file_name}.nfo")):
                if seasoninfo:
                    try:
                        self._nfo_gen.gen_episode_nfo(
                            seasoninfo,
                            scraper_tv_nfo,
                            int(media.get_season_seq()),
                            int(media.get_episode_seq()),
                            dir_path,
                            file_name,
                        )
                    except Exception as e:
                        log.error(f"[Scraper]生成 episode nfo 失败：{e}")

        # ---- season poster ----
        if scraper_tv_pic.get("season_poster"):
            try:
                season_poster = "season{}-poster".format(media.get_season_seq().rjust(2, "0"))
                seasonposter = self.fanart.get_seasonposter(
                    media_type=media.type, queryid=media.tvdb_id, season=media.get_season_seq()
                )
                if seasonposter:
                    self._downloader.download(seasonposter, dir_path, season_poster, force_pic)
                elif seasoninfo:
                    self._downloader.download(
                        ImageProxy.get_tmdbimage_url(seasoninfo.get("poster_path"), prefix="original", use_proxy=False),
                        dir_path,
                        season_poster,
                        force_pic,
                    )
            except Exception as e:
                log.error(f"[Scraper]下载 season poster 失败：{e}")

        # ---- season banner ----
        if scraper_tv_pic.get("season_banner"):
            try:
                seasonbanner = self.fanart.get_seasonbanner(
                    media_type=media.type, queryid=media.tvdb_id, season=media.get_season_seq()
                )
                if seasonbanner:
                    self._downloader.download(
                        seasonbanner,
                        tv_root,
                        "season{}-banner".format(media.get_season_seq().rjust(2, "0")),
                        force_pic,
                    )
            except Exception as e:
                log.error(f"[Scraper]下载 season banner 失败：{e}")

        # ---- season thumb ----
        if scraper_tv_pic.get("season_thumb"):
            try:
                seasonthumb = self.fanart.get_seasonthumb(
                    media_type=media.type, queryid=media.tvdb_id, season=media.get_season_seq()
                )
                if seasonthumb:
                    self._downloader.download(
                        seasonthumb,
                        tv_root,
                        "season{}-landscape".format(media.get_season_seq().rjust(2, "0")),
                        force_pic,
                    )
            except Exception as e:
                log.error(f"[Scraper]下载 season thumb 失败：{e}")

        # ---- episode thumb ----
        if scraper_tv_pic.get("episode_thumb") and str(getattr(media, "tmdb_id", "") or "").isdigit():
            try:
                episode_thumb = os.path.join(dir_path, file_name + "-thumb.jpg")
                if force_pic or not self._exists(episode_thumb):
                    episode_image = (
                        self._metadata_gateway.episode_images(
                            tv_id=media.tmdb_id,
                            season_id=media.get_season_seq(),
                            episode_id=media.get_episode_seq(),
                            original=True,
                        )
                        if self._metadata_gateway is not None
                        else ""
                    )
                    if episode_image:
                        self._downloader.download(episode_image, episode_thumb, "", force_pic)
                    elif scraper_tv_pic.get("episode_thumb_ffmpeg"):
                        video_path = os.path.join(dir_path, file_name + file_ext)
                        log.info(f"[Scraper]正在生成缩略图：{video_path} ...")
                        FfmpegProcessor().get_thumb_image_from_video(video_path=video_path, image_path=episode_thumb)
                        log.info(f"[Scraper]缩略图生成完成：{episode_thumb}")
            except Exception as e:
                log.error(f"[Scraper]下载 episode thumb 失败：{e}")

    def _fetch_douban(self, media, scraper_nfo):
        """通过网关获取豆瓣演职人员，不再直连豆瓣详情接口."""
        if not (scraper_nfo.get("credits") and scraper_nfo.get("credits_chinese")):
            return None
        if self._metadata_gateway is None:
            return None
        title = str(getattr(media, "title", "") or "").strip()
        if not title:
            return None
        context = self._metadata_context(getattr(media, "content_profile", None))
        try:
            hits = self._metadata_gateway.search(
                query=title,
                context=context,
                provider="douban",
                media_type=getattr(media, "type", None),
                limit=5,
            )
        except Exception as exc:  # noqa: BLE001 - 中文演职人员失败不阻断 NFO
            log.debug(f"[Scraper]豆瓣搜索失败: {exc}")
            return None
        hit = next((item for item in hits if str(item.get("title") or "").strip() == title), hits[0] if hits else None)
        if hit is None:
            return None
        ref = hit.get("ref") or {}
        external_id = str(ref.get("external_id") or hit.get("external_id") or "")
        if not external_id:
            return None
        try:
            record = self._metadata_gateway.lookup(
                "douban",
                external_id,
                context=context,
                media_type=getattr(media, "type", None),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[Scraper]豆瓣详情失败 {external_id}: {exc}")
            return None
        if not record:
            return None
        directors: list[dict] = []
        actors: list[dict] = []
        for credit in record.get("credits") or []:
            if not isinstance(credit, dict):
                continue
            name = str(credit.get("name") or "").strip()
            if not name:
                continue
            member = {"name": name, "latin_name": "", "character": "演员"}
            if credit.get("role") == "director":
                directors.append(member)
            elif credit.get("role") == "actor":
                actors.append(member)
        return {"title": record.get("title") or title, "directors": directors, "actors": actors}

    def _fetch_credits(self, tmdbinfo, scraper_nfo, doubaninfo):
        """获取导演/演员列表，可选中文匹配"""
        if not scraper_nfo.get("credits"):
            return [], []
        if self._metadata_gateway is None:
            log.warn("[Scraper]元数据网关不可用，跳过演职人员")
            return [], []
        directors, actors = self._metadata_gateway.directors_actors(tmdbinfo=tmdbinfo)
        if scraper_nfo.get("credits_chinese") and doubaninfo:
            directors, actors = self._credits.match(directors, actors, doubaninfo)
        return directors, actors

    def _download_images(self, media, dir_path, scraper_pic, force_pic):
        """下载电影图片"""
        if scraper_pic.get("poster"):
            poster = unwrap_display_image_url(media.get_poster_image(original=True))
            if poster and not self._portrait_image_exists(dir_path, "poster", 300):
                self._downloader.download(poster, dir_path, "poster", force_pic)
        if scraper_pic.get("backdrop"):
            backdrop = unwrap_display_image_url(media.get_backdrop_image(default=False, original=True))
            if backdrop:
                self._downloader.download(backdrop, dir_path, "fanart", force_pic)
        if str(getattr(media, "tmdb_id", "") or "").isdigit():
            for pic_type in ["background", "logo", "disc", "banner", "thumb"]:
                if not scraper_pic.get(pic_type):
                    continue
                getter = getattr(self.fanart, f"get_{pic_type}", None)
                if getter:
                    url = getter(media_type=media.type, queryid=media.tmdb_id)
                    if url:
                        self._downloader.download(url, dir_path, pic_type, force_pic)

    def _download_tv_images(self, media, tv_root, scraper_pic, force_pic):
        """下载电视剧图片"""
        if scraper_pic.get("poster"):
            poster = media.get_poster_image(original=True)
            if poster and not self._portrait_image_exists(tv_root, "poster", 300):
                self._downloader.download(poster, tv_root, "poster", force_pic)
        if scraper_pic.get("backdrop"):
            backdrop = media.get_backdrop_image(default=False, original=True)
            if backdrop:
                self._downloader.download(backdrop, tv_root, "fanart", force_pic)
        for pic_type in ["background", "logo", "disc", "banner", "thumb"]:
            if scraper_pic.get(pic_type):
                getter = getattr(self.fanart, f"get_{pic_type}", None)
                if getter:
                    url = getter(media_type=media.type, queryid=media.tvdb_id)
                    if url:
                        self._downloader.download(url, tv_root, pic_type, force_pic)
