"""System handlers 单元测试."""

from unittest.mock import patch

from app.events import Event
from app.events.constants import LIBRARY_FILE_DELETED, MEDIA_SOURCE_DELETED, MESSAGE_INCOMING
from app.services.system.handlers import (
    handle_library_file_deleted,
    handle_media_source_deleted,
    handle_message_incoming,
)


class TestSystemHandlers:
    def test_handle_message_incoming(self):
        event = Event(
            event_type=MESSAGE_INCOMING,
            payload={
                "channel": "telegram",
                "user_id": "u1",
                "user_name": "alice",
                "message": "hello",
            },
        )
        with patch("app.services.system.handlers.log") as mock_log:
            handle_message_incoming(event)
            mock_log.info.assert_called_once()
            assert "telegram" in mock_log.info.call_args[0][0]
            assert "alice" in mock_log.info.call_args[0][0]

    def test_handle_media_source_deleted(self):
        event = Event(
            event_type=MEDIA_SOURCE_DELETED,
            payload={
                "media_info": {},
                "path": "/src",
                "filename": "movie.mkv",
            },
        )
        with patch("app.services.system.handlers.log") as mock_log:
            handle_media_source_deleted(event)
            mock_log.info.assert_called_once()
            assert "/src/movie.mkv" in mock_log.info.call_args[0][0]

    def test_handle_library_file_deleted(self):
        event = Event(
            event_type=LIBRARY_FILE_DELETED,
            payload={
                "media_info": {},
                "path": "/lib",
                "filename": "movie.mkv",
            },
        )
        with patch("app.services.system.handlers.log") as mock_log:
            handle_library_file_deleted(event)
            mock_log.info.assert_called_once()
            assert "/lib/movie.mkv" in mock_log.info.call_args[0][0]
