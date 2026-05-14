"""刮削器 — 豆瓣演职人员中文名匹配"""
import log


class ChineseCredits:
    """中文演职人员匹配器 — 用豆瓣数据替换 TMDB 演职人员英文名"""

    def __init__(self, media_service):
        self._media = media_service

    def match(self, directors, actors, doubaninfo):
        """匹配并返回中文名替换后的导演/演员列表"""
        if not doubaninfo:
            log.info("【Scraper】豆瓣无该影片或剧集信息")
            return directors, actors
        if directors:
            douban_directors = doubaninfo.get("directors") or []
            for dd in douban_directors:
                dd["names"] = (dd.get("latin_name", "") or dd.get("name", "")).lower().split(" ")
            for director in directors:
                matched = self._match_person(director, douban_directors)
                if matched:
                    director["name"] = matched.get("name")
                else:
                    log.info("【Scraper】豆瓣该影片或剧集无导演 %s 信息" % director.get("name"))
        if actors:
            douban_actors = doubaninfo.get("actors") or []
            for da in douban_actors:
                da["names"] = (da.get("latin_name", "") or da.get("name", "")).lower().split(" ")
            for actor in actors:
                matched = self._match_person(actor, douban_actors)
                if matched:
                    actor["name"] = matched.get("name")
                    if matched.get("character") != "演员":
                        actor["character"] = matched.get("character", "")[2:]
                else:
                    log.info("【Scraper】豆瓣该影片或剧集无演员 %s 信息" % actor.get("name"))
        return directors, actors

    def _match_person(self, person, douban_people):
        """用 TMDB 又名 + 姓名匹配豆瓣人员"""
        aka_names = self._media.get_tmdbperson_aka_names(person.get("id")) or []
        aka_names.append(person.get("name"))
        for aka_name in aka_names:
            for dp in douban_people:
                latin_match = all(ln in aka_name.lower() for ln in dp.get("names", []))
                if latin_match or dp.get("name") == aka_name:
                    return dp
        return None
