"""测试动漫发布组/字幕组识别"""

from app.media.parser._release_groups import ReleaseGroupsMatcher


class TestAnimeReleaseGroups:
    def setup_method(self):
        self.matcher = ReleaseGroupsMatcher()

    def test_known_groups(self):
        groups = self.matcher.RELEASE_GROUPS["anime"]
        assert "LoliHouse" in groups
        assert "喵萌奶茶屋" in groups
        assert "VCB-Studio" in groups
        assert "SweetSub" in groups
        assert "Moozzi2" in groups
        assert len(groups) >= 50, f"Expected >=50 anime groups, got {len(groups)}"

    def test_match_lolihouse(self):
        result = self.matcher.match("[LoliHouse] Kimetsu no Yaiba - 01 [1080p]")
        assert "LoliHouse" in result

    def test_match_vcb(self):
        result = self.matcher.match("[VCB-Studio] Kantai Collection [BDRip]")
        assert "VCB-Studio" in result

    def test_match_anime_group_chinese(self):
        result = self.matcher.match("[喵萌奶茶屋&LoliHouse] 鬼灭之刃 [1080p]")
        assert "LoliHouse" in result

    def test_match_sweetsub(self):
        result = self.matcher.match("[SweetSub] Jujutsu Kaisen S2 [WebRip]")
        assert "SweetSub" in result

    def test_match_moozzi2(self):
        result = self.matcher.match("[Moozzi2] Tate no Yuusha [BDRip]")
        assert "Moozzi2" in result

    def test_multiple_groups(self):
        result = self.matcher.match("[VCB-Studio LoliHouse] Title [1080p]")
        assert "LoliHouse" in result
        assert "VCB-Studio" in result

    def test_no_match(self):
        result = self.matcher.match("[UnknownGroup] Some Title [1080p]")
        assert result == ""
