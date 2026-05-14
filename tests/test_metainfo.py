from unittest import TestCase

from app.media.parser._metainfo import meta_info
from tests.cases.meta_cases import meta_cases


class MetaInfoTest(TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_metainfo(self):
        for info in meta_cases:
            if not info.get("title"):
                continue
            result = meta_info(title=info.get("title") or "", subtitle=info.get("subtitle"))
            target = {
                "type": result.type.value,
                "cn_name": result.cn_name or "",
                "en_name": result.en_name or "",
                "year": result.year or "",
                "part": result.part or "",
                "season": result.get_season_string(),
                "episode": result.get_episode_string(),
                "restype": result.get_edtion_string(),
                "pix": result.resource_pix or "",
                "video_codec": result.video_encode or "",
                "audio_codec": result.audio_encode or "",
            }
            self.assertEqual(target, info.get("target"))
