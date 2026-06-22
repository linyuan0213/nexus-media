from app.utils.string_utils import StringUtils


class IndexerHelper:
    def __init__(self):
        self._indexers = []

    def set_indexers(self, indexers):
        self._indexers = indexers

    def get_all_indexers(self):
        return self._indexers

    def _match_domain(self, indexer, url):
        if not indexer.get("domain"):
            return False
        if StringUtils.url_equal(indexer.get("domain"), url):
            return True
        for alias in indexer.get("domain_aliases") or []:
            if StringUtils.url_equal(alias, url):
                return True
        return False

    def get_indexer_info(self, url, public=False):
        for idx in self._indexers:
            if not public and idx.get("public"):
                continue
            if self._match_domain(idx, url):
                return idx
        return None

    def get_indexer(
        self,
        url,
        siteid=None,
        cookie=None,
        name=None,
        rule=None,
        public=None,
        proxy=False,
        parser=None,
        ua=None,
        headers=None,
        render=None,
        language=None,
        pri=None,
    ):
        if not url:
            return None
        for idx in self._indexers:
            if self._match_domain(idx, url):
                return IndexerConf(
                    datas=idx,
                    siteid=siteid,
                    cookie=cookie,
                    name=name,
                    rule=rule,
                    public=public,
                    proxy=proxy,
                    parser=parser,
                    ua=ua,
                    headers=headers,
                    render=render,
                    builtin=True,
                    language=language,
                    pri=pri,
                )
        return None


class IndexerConf:
    def __init__(
        self,
        datas=None,
        siteid=None,
        cookie=None,
        name=None,
        rule=None,
        public=None,
        proxy=None,
        parser=None,
        ua=None,
        headers=None,
        render=None,
        builtin=True,
        language=None,
        pri=None,
    ):
        if not datas:
            return
        self.id = datas.get("id")
        self.name = name if name else datas.get("name")
        self.builtin = builtin
        self.domain = datas.get("domain")
        self.search = datas.get("search", {})
        self.batch = self.search.get("batch", {}) if builtin else {}
        self.parser = parser if parser is not None else datas.get("parser")
        self.render = render and datas.get("render")
        self.browse = datas.get("browse", {})
        self.torrents = datas.get("torrents", {})
        self.category = datas.get("category", {})
        self.siteid = siteid
        self.cookie = cookie
        self.ua = ua
        self.headers = headers
        self.rule = rule
        self.public = public if public is not None else datas.get("public")
        self.proxy = proxy if proxy is not None else datas.get("proxy")
        self.language = language if language else datas.get("language")
        self.pri = pri if pri else 0
