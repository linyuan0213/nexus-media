"""TransferEngine 目标状态返回测试."""

from unittest.mock import MagicMock


def test_transfer_returns_false_when_target_exists(tmp_path):
    from app.services.transfer_engine import TransferEngine

    engine = TransferEngine()
    engine._execute = MagicMock()
    engine.transfer_subtitles = MagicMock()
    engine.transfer_audio_tracks = MagicMock()
    engine._blacklist = MagicMock()
    src = tmp_path / "src.mkv"
    dst = tmp_path / "dst.mkv"
    src.write_bytes(b"src")
    dst.write_bytes(b"dst")

    assert engine.transfer(str(src), str(dst), "copy") is False
    engine._execute.assert_not_called()


def test_transfer_returns_true_when_target_absent(tmp_path):
    from app.services.transfer_engine import TransferEngine

    engine = TransferEngine()
    engine._execute = MagicMock()
    engine.transfer_subtitles = MagicMock()
    engine.transfer_audio_tracks = MagicMock()
    engine._blacklist = MagicMock()
    src = tmp_path / "src.mkv"
    src.write_bytes(b"src")

    assert engine.transfer(str(src), str(tmp_path / "dst.mkv"), "copy") is True
    engine._execute.assert_called_once()
