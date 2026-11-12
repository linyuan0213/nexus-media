from app.media import meta_info


def test_italian_language_tag_is_not_part_of_title():
    info = meta_info(title="LEGO Nexo Knights 2015 S04 iT 1080p WEB-DL DD5.1 AAC2.0 H.264-NOGRP")
    assert info.get_name() == "Lego Nexo Knights"
    assert info.get_season_episode_string() == "S04"


def test_multi_audio_tag_is_not_part_of_title():
    info = meta_info(title="Gu Gong Li De Da Guai Shou 2021 S01 2160p WEB-DL H.265 AAC 2Audios-CSWEB")
    assert info.get_name() == "Gu Gong Li De Da Guai Shou"
    assert info.get_season_episode_string() == "S01"
