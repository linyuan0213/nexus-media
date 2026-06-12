"""分类匹配工具函数"""


def get_category(categorys, tmdb_info):
    """
    根据 TMDB 信息与分类配置进行比较，确定所属分类
    :param categorys: 分类配置 dict[str, dict[str, str]]
    :param tmdb_info: TMDB 信息
    :return: 分类的名称
    """
    if not tmdb_info:
        return ""
    if not categorys:
        return ""
    for key, item in categorys.items():
        if not item:
            return key
        match_flag = True
        for attr, value in item.items():
            if not value:
                continue
            info_value = tmdb_info.get(attr)
            if not info_value:
                match_flag = False
                continue
            elif attr == "production_countries":
                info_values = [str(val.get("iso_3166_1")).upper() for val in info_value]
            else:
                if isinstance(info_value, list):
                    info_values = [str(val).upper() for val in info_value]
                else:
                    info_values = [str(info_value).upper()]

            if value.find(",") != -1:
                values = [str(val).upper() for val in value.split(",")]
            else:
                values = [str(value).upper()]

            if not set(values).intersection(set(info_values)):
                match_flag = False
        if match_flag:
            return key
    return ""
