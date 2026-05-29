"""测试动漫标题预处理和日文标题提取"""

from app.media.parser.anime.prepare import extract_japanese_title, prepare_title


class TestPrepareTitle:
    def test_empty_title(self):
        assert prepare_title("") == ""
        assert prepare_title(None) is None

    def test_mikan_march_tag(self):
        result = prepare_title("[喵萌奶茶屋][鬼灭之刃 柱训练篇][1080p][简日双语]")
        assert "鬼灭之刃" in result

    def test_dmhy_bracket_format(self):
        result = prepare_title("[喵萌奶茶屋&LoliHouse] 鬼灭之刃 / Kimetsu no Yaiba [01-08][WebRip 1080p]")
        assert "鬼灭之刃" in result or "Kimetsu" in result

    def test_filesize_removal(self):
        result = prepare_title("[LoliHouse] Title [1.5GB]")
        assert "1.5GB" not in result

    def test_tv_number_conversion(self):
        result = prepare_title("[TV 02][1080p] Title")
        assert "02" in result

    def test_4k_conversion(self):
        result = prepare_title("[4K] Anime Title [BDrip]")
        assert "2160p" in result.lower()

    def test_category_bracket_removal(self):
        result = prepare_title("[动画][纪录片] Title [1080p]")
        assert "动画" not in result

    def test_slash_name_handling(self):
        result = prepare_title("[LoliHouse] 鬼灭之刃 柱训练篇 / Kimetsu no Yaiba [1080p]")
        assert result

    def test_noise_stripping(self):
        result = prepare_title("[ANi] Jujutsu Kaisen S2 - 01 [1080p][CHS]")
        assert "Jujutsu" in result or result


class TestExtractJapaneseTitle:
    def test_dmhy_slash_format(self):
        result = extract_japanese_title("鬼灭之刃 柱训练篇 / Kimetsu no Yaiba: Hashira Geiko Hen [1080p]")
        assert result is not None
        assert "Kimetsu" in result

    def test_mikan_format(self):
        result = extract_japanese_title(
            "【喵萌奶茶屋】★04月新番★ 鬼灭之刃 柱训练篇 / Kimetsu no Yaiba - Hashira Geiko Hen [1080p]"
        )
        assert result and "Kimetsu" in result

    def test_no_japanese_title(self):
        result = extract_japanese_title("鬼灭之刃 柱训练篇 [1080p]")
        assert result is None

    def test_japanese_chars_skipped(self):
        result = extract_japanese_title("かんなぎ / Kannagi [1080p]")
        assert result is not None and "Kannagi" in result

    def test_multiple_slashes(self):
        result = extract_japanese_title("Chinese Name / Kantai Collection / Kancolle [1080p]")
        assert result and "a" in result.lower()
