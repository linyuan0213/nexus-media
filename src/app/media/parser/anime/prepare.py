import re

from app.utils import StringUtils

_META_CHARS = set("粤日英简繁国台港双多单语字幕音轨频内嵌封挂压效硬软中外体")

_RE_SITE_TAG = re.compile(
    r"^[【\[]?(?:[动漫画纪录片电影视连续剧集日美韩中港台海外华语综艺原盘高清]{2,}|TV|Animation|Movie|Documentar|Anime|完结][】\]]?|★\d+月新番★)",
    re.IGNORECASE,
)
_RE_FILESIZE = re.compile(r"[0-9.]+\s*[MGT]i?B(?![A-Z]+)", re.IGNORECASE)
_RE_TV_NUMBER = re.compile(r"\[TV\s+(\d{1,4})", re.IGNORECASE)
_RE_4K = re.compile(r"\[4[Kk]]", re.IGNORECASE)
_RE_KANA_TITLE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]+")
_RE_JP_EN_SUFFIX = re.compile(r"\s*[/／]\s*[^\[\]]+$")
_RE_BRACKET_GROUP = re.compile(r"^\[[^\]]+]$")
_RE_AUDIO_BITRATE = re.compile(r"\b\d{2,4}(\.\d+)?\s*(kHz|kbps|bit|bits)\b", re.IGNORECASE)
_RE_AUDIO_FORMAT = re.compile(r"\b(FLAC|ALAC|APE|WAV|AIFF|DSD|DTS|MP3|AAC|OGG|WMA|M4A|Opus)\b", re.IGNORECASE)


def prepare_title(title):
    """对命名进行预处理"""
    if not title:
        return title
    title = title.replace("[", "[").replace("]", "]").strip()

    title = _RE_SITE_TAG.sub("", title).strip()
    title = _RE_FILESIZE.sub("", title)
    title = _RE_TV_NUMBER.sub(r"[\1", title)
    title = _RE_4K.sub("2160p", title)
    # 去掉音频格式标记，避免 96kHz 的 96 被当成集数
    title = _RE_AUDIO_BITRATE.sub("", title)
    title = _RE_AUDIO_FORMAT.sub("", title)

    names = title.split("]")
    if len(names) > 1 and title.find("- ") == -1:
        titles = []
        for name in names:
            if not name:
                continue
            left_char = ""
            if name.startswith("["):
                left_char = "["
                name = name[1:]
            if name and name.find("/") != -1:
                if name.split("/")[-1].strip():
                    titles.append("{}{}".format(left_char, name.split("/")[-1].strip()))
                else:
                    titles.append("{}{}".format(left_char, name.split("/")[0].strip()))
            elif name:
                if StringUtils.is_chinese(name) and not StringUtils.is_all_chinese(name):
                    if not re.search(r"\[\d+", name, re.IGNORECASE):
                        name = re.sub(r"[\d|#:：\-()（）]", "", name).strip()
                    if not name or name.strip().isdigit():
                        continue
                    if all(c in _META_CHARS for c in name):
                        continue
                if _RE_BRACKET_GROUP.match(name):
                    titles.append(name.strip())
                else:
                    titles.append(f"{left_char}{name.strip()}")
        return "]".join(titles)
    return title


def extract_japanese_title(title):
    """从 dmhy/mikan 格式中提取日文罗马音标题用于 TMDB 匹配"""
    if not title:
        return None
    parts = re.split(r"[/／]", title)
    for part in parts:
        part = part.strip()
        if _RE_KANA_TITLE.search(part):
            continue
        if re.search(r"[a-zA-Z]{3,}", part) and not re.search(r"[\u4e00-\u9fff]", part):
            return part.strip()
    return None
