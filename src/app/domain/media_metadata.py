"""媒体元数据常量.

包含国家、语言等通用映射，供服务层调用。
"""

_CHINESE_GENRES: set[str] = {
    "剧情",
    "喜剧",
    "动作",
    "爱情",
    "惊悚",
    "犯罪",
    "冒险",
    "科幻",
    "动画",
    "悬疑",
    "恐怖",
    "战争",
    "历史",
    "传记",
    "音乐",
    "歌舞",
    "运动",
    "西部",
    "奇幻",
    "古装",
    "武侠",
    "家庭",
    "短片",
    "纪录片",
    "黑色电影",
    "情色",
    "同性",
    "儿童",
    "真人秀",
    "脱口秀",
    "舞台艺术",
}

_MAINSTREAM_GENRES: set[str] = {
    "剧情",
    "喜剧",
    "动作",
    "爱情",
    "科幻",
    "动画",
    "悬疑",
    "恐怖",
    "犯罪",
    "纪录片",
}


_LANGUAGE_MAP: dict[str, str] = {
    "en": "英语",
    "zh": "中文",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "th": "泰语",
    "vi": "越南语",
    "pl": "波兰语",
    "tr": "土耳其语",
    "nl": "荷兰语",
    "sv": "瑞典语",
    "cs": "捷克语",
    "hu": "匈牙利语",
    "el": "希腊语",
    "he": "希伯来语",
    "id": "印尼语",
    "ms": "马来语",
    "uk": "乌克兰语",
    "ro": "罗马尼亚语",
    "da": "丹麦语",
    "fi": "芬兰语",
    "no": "挪威语",
    "sk": "斯洛伐克语",
    "hr": "克罗地亚语",
    "sr": "塞尔维亚语",
    "bg": "保加利亚语",
    "bn": "孟加拉语",
    "ta": "泰米尔语",
    "te": "泰卢固语",
    "ur": "乌尔都语",
    "fa": "波斯语",
    "tl": "菲律宾语",
    "sw": "斯瓦希里语",
    "ka": "格鲁吉亚语",
    "hy": "亚美尼亚语",
    "ne": "尼泊尔语",
    "my": "缅甸语",
    "km": "高棉语",
    "lo": "老挝语",
    "si": "僧伽罗语",
    "pa": "旁遮普语",
    "gu": "古吉拉特语",
    "kn": "卡纳达语",
    "ml": "马拉雅拉姆语",
    "mr": "马拉地语",
}

_COUNTRY_MAP: dict[str, str] = {
    "us": "美国",
    "cn": "中国大陆",
    "hk": "中国香港",
    "tw": "中国台湾",
    "mo": "中国澳门",
    "jp": "日本",
    "kr": "韩国",
    "gb": "英国",
    "uk": "英国",
    "fr": "法国",
    "de": "德国",
    "ca": "加拿大",
    "au": "澳大利亚",
    "in": "印度",
    "th": "泰国",
    "ru": "俄罗斯",
    "it": "意大利",
    "es": "西班牙",
    "br": "巴西",
    "mx": "墨西哥",
    "nl": "荷兰",
    "se": "瑞典",
    "no": "挪威",
    "dk": "丹麦",
    "fi": "芬兰",
    "be": "比利时",
    "ch": "瑞士",
    "at": "奥地利",
    "pl": "波兰",
    "tr": "土耳其",
    "ar": "阿根廷",
    "id": "印度尼西亚",
    "my": "马来西亚",
    "ph": "菲律宾",
    "vn": "越南",
    "sg": "新加坡",
    "nz": "新西兰",
    "lu": "卢森堡",
    "hr": "克罗地亚",
    "ie": "爱尔兰",
    "pt": "葡萄牙",
    "gr": "希腊",
    "cz": "捷克",
    "hu": "匈牙利",
    "ua": "乌克兰",
    "ro": "罗马尼亚",
    "bg": "保加利亚",
    "rs": "塞尔维亚",
    "za": "南非",
    "eg": "埃及",
    "il": "以色列",
    "ir": "伊朗",
    "pk": "巴基斯坦",
    "bd": "孟加拉",
    "lk": "斯里兰卡",
    "ge": "格鲁吉亚",
    "am": "亚美尼亚",
    "bt": "不丹",
    "mv": "马尔代夫",
    "ke": "肯尼亚",
    "ng": "尼日利亚",
    "gh": "加纳",
    "tz": "坦桑尼亚",
    "ug": "乌干达",
    "zw": "津巴布韦",
    "zm": "赞比亚",
    "mw": "马拉维",
    "mz": "莫桑比克",
    "na": "纳米比亚",
    "bw": "博茨瓦纳",
    "sz": "斯威士兰",
    "ls": "莱索托",
    "mg": "马达加斯加",
    "mu": "毛里求斯",
    "fj": "斐济",
    "pg": "巴布亚新几内亚",
    "cl": "智利",
    "co": "哥伦比亚",
    "pe": "秘鲁",
    "ve": "委内瑞拉",
    "ec": "厄瓜多尔",
    "bo": "玻利维亚",
    "py": "巴拉圭",
    "uy": "乌拉圭",
    "gy": "圭亚那",
    "sr": "苏里南",
    "gf": "法属圭亚那",
    "mn": "蒙古",
    "kg": "吉尔吉斯斯坦",
    "tj": "塔吉克斯坦",
    "tm": "土库曼斯坦",
    "uz": "乌兹别克斯坦",
    "az": "阿塞拜疆",
    "ae": "阿联酋",
    "sa": "沙特阿拉伯",
    "qa": "卡塔尔",
    "kw": "科威特",
    "bh": "巴林",
    "om": "阿曼",
    "jo": "约旦",
    "lb": "黎巴嫩",
    "sy": "叙利亚",
    "iq": "伊拉克",
    "ye": "也门",
    "af": "阿富汗",
    "kz": "哈萨克斯坦",
    "by": "白俄罗斯",
    "lt": "立陶宛",
    "lv": "拉脱维亚",
    "ee": "爱沙尼亚",
    "si": "斯洛文尼亚",
    "mk": "北马其顿",
    "ba": "波黑",
    "al": "阿尔巴尼亚",
    "me": "黑山",
    "md": "摩尔多瓦",
    "cy": "塞浦路斯",
    "mt": "马耳他",
    "is": "冰岛",
    "li": "列支敦士登",
    "mc": "摩纳哥",
    "sm": "圣马力诺",
    "ad": "安道尔",
    "va": "梵蒂冈",
}

_MAINSTREAM_COUNTRIES: set[str] = {
    "中国大陆",
    "中国香港",
    "中国台湾",
    "中国澳门",
    "美国",
    "日本",
    "韩国",
    "英国",
    "法国",
    "德国",
    "加拿大",
    "澳大利亚",
    "印度",
    "泰国",
    "俄罗斯",
    "意大利",
    "西班牙",
    "巴西",
    "墨西哥",
    "荷兰",
    "瑞典",
    "挪威",
    "丹麦",
    "芬兰",
    "比利时",
    "瑞士",
    "奥地利",
    "波兰",
    "土耳其",
    "阿根廷",
    "印度尼西亚",
    "马来西亚",
    "菲律宾",
    "越南",
    "新加坡",
    "新西兰",
    "卢森堡",
    "克罗地亚",
    "爱尔兰",
    "葡萄牙",
    "希腊",
    "捷克",
    "匈牙利",
    "乌克兰",
    "罗马尼亚",
    "保加利亚",
    "塞尔维亚",
    "南非",
    "埃及",
    "以色列",
    "伊朗",
    "巴基斯坦",
    "孟加拉",
}


def normalize_genres(genres: list[str]) -> list[str]:
    """过滤类型，只保留主流类型，其他归入'其他'。"""
    if not genres:
        return []
    result: set[str] = set()
    has_other = False
    for g in genres:
        if g in _MAINSTREAM_GENRES:
            result.add(g)
        else:
            has_other = True
    ordered = sorted(result)
    if has_other:
        ordered.append("其他")
    return ordered


_COUNTRY_LANGUAGE_MAP: dict[str, str] = {
    "中国大陆": "中文",
    "中国香港": "中文",
    "中国台湾": "中文",
    "中国澳门": "中文",
    "美国": "英语",
    "英国": "英语",
    "加拿大": "英语",
    "澳大利亚": "英语",
    "新西兰": "英语",
    "爱尔兰": "英语",
    "日本": "日语",
    "韩国": "韩语",
    "法国": "法语",
    "德国": "德语",
    "奥地利": "德语",
    "瑞士": "德语",
    "西班牙": "西班牙语",
    "墨西哥": "西班牙语",
    "阿根廷": "西班牙语",
    "意大利": "意大利语",
    "俄罗斯": "俄语",
    "泰国": "泰语",
    "印度": "印地语",
    "巴西": "葡萄牙语",
    "葡萄牙": "葡萄牙语",
    "荷兰": "荷兰语",
    "比利时": "荷兰语",
    "瑞典": "瑞典语",
    "挪威": "挪威语",
    "丹麦": "丹麦语",
    "芬兰": "芬兰语",
    "波兰": "波兰语",
    "土耳其": "土耳其语",
    "印度尼西亚": "印尼语",
    "马来西亚": "马来语",
    "菲律宾": "菲律宾语",
    "越南": "越南语",
    "新加坡": "中文",
    "以色列": "希伯来语",
    "伊朗": "波斯语",
    "巴基斯坦": "乌尔都语",
    "孟加拉": "孟加拉语",
    "乌克兰": "乌克兰语",
    "罗马尼亚": "罗马尼亚语",
    "保加利亚": "保加利亚语",
    "塞尔维亚": "塞尔维亚语",
    "捷克": "捷克语",
    "匈牙利": "匈牙利语",
    "希腊": "希腊语",
    "克罗地亚": "克罗地亚语",
    "南非": "英语",
    "埃及": "阿拉伯语",
}


def derive_language_from_country(countries: list[str]) -> str | None:
    """根据国家推断主要语言，仅作为 fallback。"""
    for c in countries:
        if c in _COUNTRY_LANGUAGE_MAP:
            return _COUNTRY_LANGUAGE_MAP[c]
    return None


def normalize_language(code: str) -> str:
    """将语言代码映射为中文名称。"""
    return _LANGUAGE_MAP.get(code.lower(), code)


def normalize_languages(languages) -> list[str]:
    """标准化语言列表。"""
    if not languages:
        return []
    if isinstance(languages, str):
        return [normalize_language(languages)]
    return [normalize_language(str(code)) for code in languages if code]


def normalize_country(raw: str) -> str:
    """将国家代码或名称映射为中文名称。"""
    return _COUNTRY_MAP.get(raw.lower().strip(), raw.strip())


def normalize_countries(countries) -> list[str]:
    """标准化国家列表，主流国家保留原名，非主流归入'其他'。"""
    if not countries:
        return []
    if isinstance(countries, str):
        raw = [c.strip() for c in countries.split() if c.strip()]
    else:
        raw = [str(c).strip() for c in countries if c]

    result: set[str] = set()
    has_other = False
    for c in raw:
        mapped = normalize_country(c)
        if mapped in _MAINSTREAM_COUNTRIES:
            result.add(mapped)
        else:
            has_other = True
    ordered = sorted(result)
    if has_other:
        ordered.append("其他")
    return ordered


__all__ = [
    "_CHINESE_GENRES",
    "_MAINSTREAM_GENRES",
    "_LANGUAGE_MAP",
    "_COUNTRY_MAP",
    "_MAINSTREAM_COUNTRIES",
    "_COUNTRY_LANGUAGE_MAP",
    "derive_language_from_country",
    "normalize_genres",
    "normalize_language",
    "normalize_languages",
    "normalize_country",
    "normalize_countries",
]
