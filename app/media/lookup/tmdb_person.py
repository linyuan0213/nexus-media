import zhconv

from app.helper.image_proxy_helper import ImageProxyHelper
from app.media.lookup.tmdb_client import TmdbClient
from app.utils import StringUtils


class TmdbPerson:
    """TMDB 人员查询"""

    def __init__(self, client: TmdbClient):
        self.client = client

    def search(self, name):
        if not self.client.search:
            return []
        try:
            return self._dict_persons(self.client.search.people({"query": name}))
        except Exception as err:
            print(str(err))
            return []

    def get_chinese_name(self, person_id=None, person_info=None):
        if not self.client.person:
            return ""
        if not person_info and not person_id:
            return ""
        name = ""
        alter_names = []
        try:
            if not person_info:
                person_info = self.client.person.details(person_id)
            if not person_info:
                return ""
            aka_names = person_info.get("also_known_as", []) or []
        except Exception as err:
            print(str(err))
            return ""
        for aka_name in aka_names:
            if StringUtils.is_chinese(aka_name):
                alter_names.append(aka_name)
        if len(alter_names) == 1:
            name = alter_names[0]
        elif len(alter_names) > 1:
            for alter_name in alter_names:
                if alter_name == zhconv.convert(alter_name, "zh-hans"):
                    name = alter_name
        return name

    def get_aka_names(self, person_id):
        if not self.client.person:
            return []
        try:
            return self.client.person.details(person_id).get("also_known_as", []) or []
        except Exception as err:
            print(str(err))
            return []

    def _dict_persons(self, infos, chinese=True):
        if not infos:
            return []
        ret_infos = []
        for info in infos:
            if chinese:
                name = self.get_chinese_name(person_id=info.get("id")) or info.get("name")
            else:
                name = info.get("name")
            tmdbid = info.get("id")
            image = (
                ImageProxyHelper.get_tmdbimage_url(info.get("profile_path"), prefix="h632")
                if info.get("profile_path")
                else ""
            )
            ret_infos.append(
                {
                    "id": tmdbid,
                    "name": name,
                    "role": info.get("name") if info.get("name") != name else "",
                    "image": image,
                }
            )
        return ret_infos
