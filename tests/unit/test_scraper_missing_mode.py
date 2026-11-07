"""增量刮削判定：已有 NFO/海报的文件应跳过."""

from unittest.mock import MagicMock

from PIL import Image

from app.domain.media_types import ProviderMediaType
from app.media.metadata.models import Credit, FieldValue, ImageAsset, MediaMetadata, ProviderRef
from app.media.scraper import Scraper
from app.media.scraper.nfo_generator import NfoGenerator


def _build_scraper() -> Scraper:
    system_config = MagicMock()
    system_config.get.return_value = {
        "scraper_nfo": {"movie": {"basic": True}},
        "scraper_pic": {"movie": {"poster": True}},
    }
    return Scraper(media_service=MagicMock(), system_config=system_config)


def test_has_scraped_metadata_requires_nfo_and_poster(tmp_path):
    media_file = tmp_path / "Test.Movie.2020.mkv"
    media_file.write_bytes(b"x")
    scraper = _build_scraper()

    assert scraper._has_scraped_metadata(str(media_file)) is False

    (tmp_path / "Test.Movie.2020.nfo").write_text("<movie><plot>剧情</plot></movie>", encoding="utf-8")
    assert scraper._has_scraped_metadata(str(media_file)) is False

    (tmp_path / "poster.jpg").write_bytes(b"x")
    assert scraper._has_scraped_metadata(str(media_file)) is True


def test_has_scraped_metadata_skips_when_nothing_configured(tmp_path):
    media_file = tmp_path / "Test.Movie.2020.mkv"
    media_file.write_bytes(b"x")
    system_config = MagicMock()
    system_config.get.return_value = {"scraper_nfo": {}, "scraper_pic": {}}
    scraper = Scraper(media_service=MagicMock(), system_config=system_config)

    assert scraper._has_scraped_metadata(str(media_file)) is True


def test_incomplete_nfo_is_still_missing_even_with_poster(tmp_path):
    media_file = tmp_path / "Test.Movie.2020.mkv"
    media_file.write_bytes(b"x")
    (tmp_path / "Test.Movie.2020.nfo").write_text(
        "<movie><plot></plot><rating>0</rating><fileinfo /></movie>", encoding="utf-8"
    )
    (tmp_path / "poster.jpg").write_bytes(b"x")
    scraper = _build_scraper()

    assert scraper._has_scraped_metadata(str(media_file)) is False


def test_incomplete_existing_nfo_needs_rewrite(tmp_path):
    media_file = tmp_path / "Test.Movie.2020.mkv"
    media_file.write_bytes(b"x")
    (tmp_path / "Test.Movie.2020.nfo").write_text(
        "<movie><plot></plot><rating>0</rating><fileinfo /></movie>", encoding="utf-8"
    )
    scraper = _build_scraper()

    assert scraper._nfo_needs_rewrite(str(tmp_path), "Test.Movie.2020", ProviderMediaType.MOVIE)


def test_complete_existing_nfo_does_not_need_rewrite(tmp_path):
    media_file = tmp_path / "Test.Movie.2020.mkv"
    media_file.write_bytes(b"x")
    (tmp_path / "Test.Movie.2020.nfo").write_text("<movie><plot>剧情</plot></movie>", encoding="utf-8")
    scraper = _build_scraper()

    assert not scraper._nfo_needs_rewrite(str(tmp_path), "Test.Movie.2020", ProviderMediaType.MOVIE)


def test_has_scraped_metadata_requires_poster_when_only_fanart_exists(tmp_path):
    media_file = tmp_path / "TC-268.mp4"
    media_file.write_bytes(b"x")
    (tmp_path / "TC-268.nfo").write_text("<movie><plot>剧情</plot></movie>", encoding="utf-8")
    (tmp_path / "fanart.jpg").write_bytes(b"x")
    system_config = MagicMock()
    system_config.get.return_value = {
        "scraper_nfo": {"movie": {"basic": True}},
        "scraper_pic": {"movie": {"poster": True, "fanart": True}},
    }
    scraper = Scraper(media_service=MagicMock(), system_config=system_config)

    assert scraper._has_scraped_metadata(str(media_file)) is False

    (tmp_path / "poster.jpg").write_bytes(b"x")
    assert scraper._has_scraped_metadata(str(media_file)) is True


def test_ensure_snapshot_images_fills_missing_poster_and_keeps_fanart():
    metadata_gateway = MagicMock()
    metadata_gateway.lookup.return_value = {
        "images": {"poster": [{"type": "poster", "url": "https://example.com/p.jpg"}]}
    }
    scraper = Scraper(media_service=MagicMock(), system_config=MagicMock(), metadata_gateway=metadata_gateway)
    snapshot = MediaMetadata(
        identity_id="x",
        media_type=ProviderMediaType.MOVIE,
        content_profile="demo",
        refs=[ProviderRef(provider="mgstage", external_id="TC-268")],
        fields={"title": FieldValue(value="TC-268", provider="demo", external_id="TC-268")},
        images={"fanart": [ImageAsset(type="fanart", url="https://example.com/f.jpg")]},
    )

    scraper._ensure_snapshot_images(snapshot)

    assert snapshot.images["poster"][0].url == "https://example.com/p.jpg"
    assert snapshot.images["fanart"][0].url == "https://example.com/f.jpg"


def test_ensure_snapshot_images_builds_credits_from_actor_fallback():
    scraper = Scraper(media_service=MagicMock(), system_config=MagicMock(), metadata_gateway=MagicMock())
    snapshot = MediaMetadata(
        identity_id="x",
        media_type=ProviderMediaType.MOVIE,
        content_profile="demo",
        fields={"title": FieldValue(value="SHKD-724", provider="demo", external_id="SHKD-724")},
        images={"poster": [ImageAsset(type="poster", url="https://example.com/p.jpg")]},
        extra={
            "demo.actresses": ["桜木凛"],
            "actor_fallback": ["桜木凛"],
            "actor_images": {"桜木凛": "https://example.com/a.jpg"},
        },
    )

    scraper._ensure_snapshot_images(snapshot)

    assert [(credit.name, credit.role) for credit in snapshot.credits] == [("桜木凛", "actor")]
    assert snapshot.credits[0].image_url == "https://example.com/a.jpg"


def test_ensure_poster_file_only_uses_portrait_fanart(tmp_path):
    Image.new("RGB", (600, 800), (200, 30, 30)).save(tmp_path / "fanart.jpg")
    scraper = _build_scraper()

    poster = scraper._ensure_poster_file(str(tmp_path))

    assert poster == str(tmp_path / "poster.jpg")
    assert (tmp_path / "poster.jpg").exists()


def test_ensure_poster_file_rejects_horizontal_fanart(tmp_path):
    Image.new("RGB", (800, 539), (200, 30, 30)).save(tmp_path / "fanart.jpg")
    scraper = _build_scraper()

    assert scraper._ensure_poster_file(str(tmp_path)) is None
    assert not (tmp_path / "poster.jpg").exists()


def test_normalize_crops_landscape_full_jacket_to_portrait(tmp_path):
    poster = tmp_path / "poster.jpg"
    Image.new("RGB", (1920, 1080), (200, 30, 30)).save(poster)
    scraper = _build_scraper()

    scraper._normalize_snapshot_poster(None, str(tmp_path))

    with Image.open(poster) as img:
        assert img.height > img.width
    assert (tmp_path / "fanart.jpg").exists()


def test_synthetic_landscape_crop_poster_is_removed(tmp_path):
    fanart = Image.new("RGB", (800, 539), (200, 30, 30))
    fanart.save(tmp_path / "fanart.jpg")
    target_w = int(539 * 2 / 3)
    fanart.crop((800 - target_w, 0, 800, 539)).save(tmp_path / "poster.jpg")
    scraper = _build_scraper()

    assert scraper._portrait_image_exists(str(tmp_path), "poster") is False
    assert not (tmp_path / "poster.jpg").exists()


def test_download_candidates_preserves_existing_portrait_poster(tmp_path):
    Image.new("RGB", (600, 800), (200, 30, 30)).save(tmp_path / "poster.jpg")
    scraper = _build_scraper()
    scraper._downloader = MagicMock()

    ok = scraper._download_candidates(["https://example.com/bad.jpg"], str(tmp_path), "poster", True, 300, 300)

    assert ok is True
    scraper._downloader.download.assert_not_called()


def test_white_placeholder_poster_is_removed(tmp_path):
    poster = tmp_path / "poster.jpg"
    Image.new("RGB", (800, 539), "white").save(poster)
    snapshot = MediaMetadata(identity_id="x", content_profile="demo")
    scraper = _build_scraper()

    scraper._normalize_snapshot_poster(snapshot, str(tmp_path))

    assert not poster.exists()


def test_placeholder_poster_is_detected(tmp_path):
    poster = tmp_path / "poster.jpg"
    Image.new("RGB", (147, 200), "white").save(poster)
    scraper = _build_scraper()
    assert scraper._is_placeholder_image(str(poster)) is True


def test_landscape_custom_cover_is_cropped_to_front_panel(tmp_path):
    poster = tmp_path / "poster.jpg"
    Image.new("RGB", (800, 539), (200, 30, 30)).save(poster)
    snapshot = MediaMetadata(identity_id="x", content_profile="demo")
    scraper = _build_scraper()

    scraper._normalize_snapshot_poster(snapshot, str(tmp_path))

    with Image.open(poster) as img:
        assert img.height > img.width
    assert (tmp_path / "fanart.jpg").exists()


def test_download_candidates_skips_placeholder_and_tries_beyond_five_sources(tmp_path):
    scraper = _build_scraper()
    urls = [f"https://img.example/p{index}.jpg" for index in range(7)]

    def _download(url, target_dir, file_name, force):
        index = int(str(url).rsplit("/p", 1)[-1].split(".")[0])
        if index < 6:
            Image.new("RGB", (800, 539), "white").save(tmp_path / f"{file_name}.jpg")
        else:
            Image.new("RGB", (600, 800), (200, 30, 30)).save(tmp_path / f"{file_name}.jpg")
        return True

    scraper._downloader = MagicMock()
    scraper._downloader.download.side_effect = _download

    ok = scraper._download_candidates(urls, str(tmp_path), "poster", False, 300, 300, require_portrait=True)

    assert ok is True
    assert scraper._downloader.download.call_count == 7
    with Image.open(tmp_path / "poster.jpg") as img:
        assert img.height > img.width


def test_ensure_poster_file_ignores_placeholder_fanart(tmp_path):
    Image.new("RGB", (800, 539), "white").save(tmp_path / "fanart.jpg")
    scraper = _build_scraper()

    assert scraper._ensure_poster_file(str(tmp_path)) is None
    assert not (tmp_path / "poster.jpg").exists()


def test_prune_missing_image_assets_removes_dangling_nfo_references(tmp_path):
    Image.new("RGB", (600, 800), (200, 30, 30)).save(tmp_path / "poster.jpg")
    snapshot = MediaMetadata(
        identity_id="x",
        content_profile="demo",
        images={
            "poster": [ImageAsset(type="poster", url="https://example.com/p.jpg")],
            "fanart": [ImageAsset(type="fanart", url="https://example.com/f.jpg")],
        },
    )
    scraper = _build_scraper()

    scraper._prune_missing_image_assets(snapshot, str(tmp_path))

    assert snapshot.images.get("poster")
    assert "fanart" not in snapshot.images


def test_snapshot_nfo_honors_force_flags(tmp_path):
    snapshot = MediaMetadata(
        identity_id="x",
        content_profile="demo",
        extra={"nfo.force_basic": True, "nfo.force_credits": True},
        fields={
            "title": FieldValue(value="DEMO-247 标题", provider="demo", external_id="DEMO-247"),
            "overview": FieldValue(value="剧情", provider="demo", external_id="DEMO-247"),
        },
        credits=[Credit(name="演示演员", role="actor")],
    )
    downloader = MagicMock()
    NfoGenerator(downloader).gen_movie_nfo_from_snapshot(
        snapshot, {"basic": False, "credits": False}, str(tmp_path), "DEMO-247"
    )

    doc = downloader.save_nfo.call_args.args[0]
    xml = doc.toxml()
    assert "<title>DEMO-247 标题</title>" in xml
    assert "<plot>" in xml and "剧情" in xml
    assert "<name>演示演员</name>" in xml
