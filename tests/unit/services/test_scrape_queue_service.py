"""ScrapeQueueService 异步刮削队列单元测试."""

import threading
from unittest.mock import MagicMock

from app.db.repositories.identity_resolver import IdentityResolver
from app.domain.lifecycle import LifecycleStage
from app.domain.mediatypes import MediaType
from app.infrastructure.task_queue import Task
from app.infrastructure.thread import ThreadExecutor
from app.media.models import MediaInfo
from app.services.scrape_queue_service import ScrapeQueueService
from app.utils.json_utils import JsonUtils


class TestScrapeQueueService:
    def teardown_method(self):
        ThreadExecutor.reset_instance("scrape")

    def test_submit_file_scrape_executes_async(self):
        scraper = MagicMock()
        done = threading.Event()

        def _scrape(**kwargs):
            done.set()
            return True

        scraper.gen_scraper_files.side_effect = _scrape
        svc = ScrapeQueueService(scraper=scraper, max_workers=1)

        media = MediaInfo(title="Test", type=MediaType.MOVIE, identity_id="01DEMO")
        svc.submit_file_scrape(media, "/dst", "Test.mkv", ".mkv")

        assert done.wait(timeout=5)
        scraper.gen_scraper_files.assert_called_once()
        call_kwargs = scraper.gen_scraper_files.call_args.kwargs
        assert call_kwargs["dir_path"] == "/dst"
        assert call_kwargs["file_name"] == "Test.mkv"

    def test_submit_file_scrape_isolates_media_copy(self):
        scraper = MagicMock()
        done = threading.Event()

        def capture(media, **kwargs):
            captured.append(media)
            done.set()
            return True

        captured = []
        scraper.gen_scraper_files.side_effect = capture
        svc = ScrapeQueueService(scraper=scraper, max_workers=1)

        media = MediaInfo(title="Test", type=MediaType.MOVIE, identity_id="01DEMO")
        svc.submit_file_scrape(media, "/dst", "Test.mkv", ".mkv")
        assert done.wait(timeout=5)
        assert len(captured) == 1
        assert captured[0] is not media  # 深拷贝隔离，避免与转移线程共享对象

    def test_scrape_success_projects_in_library(self):
        scraper = MagicMock()
        scraper.gen_scraper_files.return_value = True
        lifecycle = MagicMock()
        svc = ScrapeQueueService(scraper=scraper, max_workers=1, lifecycle=lifecycle)

        media = MediaInfo(title="Test", type=MediaType.MOVIE, identity_id="01DEMO")
        task = Task.create(
            "scrape:file",
            "scrape.file",
            {"media": JsonUtils.model_to_jsonable(media)},
        )
        result = svc._run_file_payload(task.payload, task)

        assert result == {"scraped": True}
        stages = [call.kwargs["stage"] for call in lifecycle.record_media.call_args_list]
        assert stages == [
            LifecycleStage.SCRAPING,
            LifecycleStage.SCRAPED,
            LifecycleStage.IN_LIBRARY,
        ]

    def test_submit_folder_scrape_executes_async(self):
        scraper = MagicMock()
        done = threading.Event()
        scraper.folder_scraper.side_effect = lambda **kwargs: done.set()
        svc = ScrapeQueueService(scraper=scraper, max_workers=1)

        svc.submit_folder_scrape("/media/Test", mode="force_all")
        assert done.wait(timeout=5)
        scraper.folder_scraper.assert_called_once_with(path="/media/Test", mode="force_all", dst_backend=None)

    def test_scrape_failure_does_not_raise(self):
        scraper = MagicMock()
        scraper.gen_scraper_files.side_effect = RuntimeError("boom")
        svc = ScrapeQueueService(scraper=scraper, max_workers=1)

        media = MediaInfo(title="Test", type=MediaType.MOVIE, identity_id="01DEMO")
        svc.submit_file_scrape(media, "/dst", "Test.mkv", ".mkv")

        # 不抛异常即为通过；等待任务结束
        import time

        time.sleep(0.5)

    def test_duplicate_finalize_skips_notification_when_already_in_library(self):
        lifecycle = MagicMock()
        lifecycle.is_in_library.return_value = True
        message = MagicMock()
        svc = ScrapeQueueService(scraper=MagicMock(), max_workers=1, lifecycle=lifecycle, message=message)

        media = MediaInfo(title="DEMO-001", type=MediaType.MOVIE, identity_id="01DEMO")
        svc.finalize_duplicate(media, {"in_from": "downloaders", "exist_filenum": 1})

        message.send_transfer_movie_message.assert_not_called()

    def test_duplicate_finalize_skips_notification_when_previously_in_library(self):
        lifecycle = MagicMock()
        lifecycle.is_in_library.return_value = False
        lifecycle.has_been_in_library.return_value = True
        message = MagicMock()
        svc = ScrapeQueueService(scraper=MagicMock(), max_workers=1, lifecycle=lifecycle, message=message)

        media = MediaInfo(title="DEMO-001", type=MediaType.MOVIE, identity_id="01DEMO")
        svc.finalize_duplicate(media, {"in_from": "downloaders", "exist_filenum": 1})

        message.send_transfer_movie_message.assert_not_called()


class TestFinalizeReceipt:
    def test_duplicate_finalize_skipped_by_receipt(self):
        message = MagicMock()
        event_bus = MagicMock()
        receipt = MagicMock()
        receipt.claim.return_value = False
        svc = ScrapeQueueService(
            scraper=MagicMock(),
            max_workers=1,
            message=message,
            event_bus=event_bus,
            receipt_repo=receipt,
        )
        media = MediaInfo(title="DEMO-001", type=MediaType.MOVIE, identity_id="01DEMO")

        svc._finalize(media, {"in_from": "downloaders", "exist_filenum": 1}, metadata_ok=True)

        message.send_transfer_movie_message.assert_not_called()
        event_bus.publish.assert_not_called()

    def test_duplicate_finalize_can_skip_notification(self):
        message = MagicMock()
        event_bus = MagicMock()
        receipt = MagicMock()
        receipt.claim.return_value = True
        svc = ScrapeQueueService(
            scraper=MagicMock(),
            max_workers=1,
            message=message,
            event_bus=event_bus,
            receipt_repo=receipt,
        )
        media = MediaInfo(title="DEMO-001", type=MediaType.MOVIE, identity_id="01DEMO")

        svc._finalize(
            media,
            {"in_from": "downloaders", "exist_filenum": 1, "notify": False},
            metadata_ok=True,
        )

        message.send_transfer_movie_message.assert_not_called()
        event_bus.publish.assert_called_once()

    def test_first_finalize_claims_receipt(self):
        message = MagicMock()
        event_bus = MagicMock()
        receipt = MagicMock()
        receipt.claim.return_value = True
        svc = ScrapeQueueService(
            scraper=MagicMock(),
            max_workers=1,
            message=message,
            event_bus=event_bus,
            receipt_repo=receipt,
        )
        media = MediaInfo(title="DEMO-001", type=MediaType.MOVIE, identity_id="01DEMO")

        svc._finalize(media, {"in_from": "downloaders", "exist_filenum": 1}, metadata_ok=True)

        receipt.claim.assert_called_once()
        message.send_transfer_movie_message.assert_called_once()


def test_finalize_receipt_key_resolves_tmdb_to_identity():
    identity_repo = MagicMock()
    identity_repo.find_by_ref.return_value = type("Identity", (), {"IDENTITY_ID": "01ABC"})()
    svc = ScrapeQueueService(scraper=MagicMock(), max_workers=1, identity_resolver=IdentityResolver(identity_repo))
    tmdb_only = MediaInfo(
        title="DEMO-001",
        type=MediaType.ANIME,
        tmdb_id="220542",
        begin_season=1,
        begin_episode=54,
        end_episode=54,
    )
    with_identity = MediaInfo(
        title="DEMO-001",
        type=MediaType.ANIME,
        tmdb_id="220542",
        identity_id="01ABC",
        begin_season=1,
        begin_episode=54,
        end_episode=54,
    )
    assert svc._ensure_identity(tmdb_only) is True
    assert svc._finalize_receipt_key(tmdb_only) == svc._finalize_receipt_key(with_identity)
    assert svc._finalize_receipt_key(tmdb_only).startswith("id:01ABC|")
