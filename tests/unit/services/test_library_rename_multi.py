"""多实例媒体库批量重命名测试。"""

from unittest.mock import MagicMock

from app.services.transfer.library_rename_metadata import LibraryMetadataResolver
from app.services.transfer.library_rename_models import RenameScope


def test_metadata_prepare_reads_selected_instance():
    media_server = MagicMock()
    media_server.get_libraries.return_value = [{"id": "lib-demo"}]
    media_server.get_items.return_value = []
    resolver = LibraryMetadataResolver(media_server, MagicMock(), MagicMock())

    resolver.prepare(True, server_id=2)

    media_server.get_libraries.assert_called_once_with(2)
    media_server.get_items.assert_called_once_with("lib-demo", 2)


def test_rename_scope_persists_server_id():
    scope = RenameScope(server_id=2)
    assert scope.to_dict()["server_id"] == 2
