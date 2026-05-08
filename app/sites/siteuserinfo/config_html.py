# -*- coding: utf-8 -*-
"""
配置驱动的 HTML 站点用户信息解析器

架构自动检测 → 委托对应模块解析：
- NexusPhp → nexus_php.py
- Gazelle  → gazelle.py
- Unit3d   → unit3d.py
- Discuz   → discuz.py
- SmallHorse → small_horse.py
- JSON user_info.type=html → CSS 选择器
"""
import json
import re
from urllib.parse import urljoin
from lxml import etree

import log
from app.sites.engine import SiteEngine
from app.sites.siteuserinfo import nexus_php, gazelle, unit3d, discuz, small_horse
from app.utils import RequestUtils, StringUtils
from app.utils.config_tools import get_proxies

_ARCH_PARSERS = [
    (gazelle.is_gazelle, gazelle.parse),
    (unit3d.is_unit3d, unit3d.parse),
    (discuz.is_discuz, discuz.parse),
    (small_horse.is_small_horse, small_horse.parse),
    (nexus_php.is_nexusphp, nexus_php.parse),
]


class ConfigHtmlUserInfo:
    order = 5

    def __init__(self, site_def, site_name, url, site_cookie,
                 site_headers=None, ua="", emulate=False, proxy=False,
                 session=None, json_data=None):
        self.site_name = site_name
        self.site_url = url
        self._def = site_def
        self._cookie = site_cookie
        self._headers = site_headers or {}
        self._ua = ua
        self._emulate = emulate
        self._proxy = proxy
        self._session = session
        self._proxies = get_proxies() if proxy else None
        self._index_html = json_data or ""
        self._base_url_str = self.site_url.rstrip("/") if self.site_url else ""

        self.username = None
        self.userid = None
        self.user_level = None
        self.join_at = None
        self.bonus = 0.0
        self.upload = 0
        self.download = 0
        self.ratio = 0.0
        self.seeding = 0
        self.seeding_size = 0
        self.seeding_info = "[]"
        self.leeching = 0
        self.leeching_size = 0
        self.message_unread = 0
        self.message_unread_contents = []
        self.err_msg = None
        self.site_favicon = None

    @classmethod
    def match(cls, html_text):
        return False

    @property
    def schema(self):
        return "ConfigHtml"

    def site_schema(self):
        return "ConfigHtml"

    def parse(self):
        cfg = self._def.user_info if isinstance(self._def.user_info, dict) else {}
        if cfg.get("type") == "html" and cfg.get("fields"):
            nexus_php._parse_userid(self)
            self._parse_fields(cfg)
            self._parse_seeding(cfg)
            return
        for check, parser in _ARCH_PARSERS:
            if check(self):
                parser(self)
                break
        if cfg.get("seeding") and not self.seeding:
            self._parse_seeding(cfg)

    def _parse_fields(self, cfg):
        fields = cfg.get("fields", {})
        if not fields:
            return
        page = cfg.get("page")
        html_text = self._index_html
        if page:
            url = urljoin(self._base_url_str + "/", page.format(userid=self.userid or ""))
            html_text = self._fetch_html(url)
        if not html_text:
            return
        doc = etree.HTML(html_text)
        if doc is None:
            return
        for fname, fcfg in fields.items():
            val = self._extract_field(doc, html_text, fcfg)
            if val is not None:
                setattr(self, fname, val)
        if self.upload and self.download and not self.ratio:
            self.ratio = round(self.upload / self.download, 2) if self.download else 0

    def _extract_field(self, doc, html_text, cfg):
        selector = cfg.get("selector", "")
        extract = cfg.get("extract", "text")
        attr = cfg.get("attribute", "")
        if not selector:
            return None
        raw = None
        try:
            els = doc.cssselect(selector)
        except Exception:
            els = []
        if not els:
            try:
                els = doc.xpath(selector)
            except Exception:
                els = []
        if els:
            raw = (els[0].get(attr, "") if attr else els[0].xpath("string(.)").strip())
        pattern = cfg.get("pattern", "")
        if pattern and raw:
            m = re.search(pattern, str(raw), re.I)
            if m:
                raw = m.group(1) if m.lastindex else m.group(0)
        if not raw and extract == "regex" and pattern and html_text:
            m = re.search(pattern, html_text, re.I)
            if m:
                raw = m.group(1) if m.lastindex else m.group(0)
        if raw is None:
            return None
        if extract == "filesize":
            return StringUtils.num_filesize(str(raw))
        elif extract == "float":
            return StringUtils.str_float(str(raw))
        elif extract == "int":
            return StringUtils.str_int(str(raw))
        elif extract == "datetime":
            return StringUtils.unify_datetime_str(str(raw))
        elif extract == "text":
            return str(raw).strip()
        return raw

    def _parse_seeding(self, cfg):
        sc = cfg.get("seeding", {})
        if not sc:
            return
        if sc.get("type") == "api":
            self._parse_seeding_api(sc)
            return
        page = sc.get("page") or "getusertorrentlistajax.php?userid={userid}&type=seeding"
        ls = sc.get("list_selector", "table.torrents tr")
        ss = sc.get("size_selector", "td:nth-child(4)")
        sd = sc.get("seeders_selector", "td:nth-child(5) a")
        uid = self.userid or ""
        pn = 1
        total = 0
        info = []
        has_pagination = "{page}" in page
        while True:
            url = urljoin(self._base_url_str + "/", page.format(userid=str(uid), page=pn))
            referer = f"{self._base_url_str}/userdetails.php?id={uid}" if uid else None
            is_ajax_url = has_pagination or "ajax" in page.lower()
            html_text = self._fetch_html(url, referer=referer, use_ajax_headers=is_ajax_url)
            if not html_text:
                break
            total_regex = sc.get("total_regex")
            total_match = None
            if total_regex:
                m = re.search(total_regex, html_text, re.I)
                if m and m.group(1) and m.group(2):
                    total_match = m
            else:
                for pat in [r"<b>(\d+)</b>条记录 Total: ([\d.]+\s*[KMGT]B)",
                            r"<b>(\d+)</b>\s*条记录，共计<b>([\d.]+\s*[KMGT]B)</b>"]:
                    m = re.search(pat, html_text, re.I)
                    if m and m.group(1) and m.group(2):
                        total_match = m
                        break
            if total_match:
                self.seeding = StringUtils.str_int(total_match.group(1))
                self.seeding_size = StringUtils.num_filesize(total_match.group(2))
                return
            doc = etree.HTML(html_text.replace(r'\/', '/'))
            if doc is None:
                break
            rows = doc.cssselect(ls)
            if not rows:
                try:
                    rows = doc.xpath(ls)
                except Exception:
                    rows = []
            cnt = 0
            for row in rows:
                if row.xpath(".//td[contains(@class,'colhead')]") or row.xpath(".//th"):
                    continue
                try:
                    se = row.cssselect(ss)
                    if not se:
                        se = row.xpath(ss)
                    sd_els = row.cssselect(sd)
                    if not sd_els:
                        sd_els = row.xpath(sd)
                    if not se:
                        continue
                    size = StringUtils.num_filesize(se[0].xpath("string(.)").strip())
                    seeders = StringUtils.str_int(sd_els[0].xpath("string(.)").strip()) if sd_els else 0
                    total += size
                    cnt += 1
                    info.append([seeders, size])
                except Exception:
                    pass
            if cnt == 0 or not has_pagination:
                break
            pn += 1
        self.seeding_size = total
        self.seeding_info = json.dumps(info)

    def _parse_seeding_api(self, sc):
        method = sc.get("method", "GET").upper()
        path = sc.get("path", "").format(userid=self.userid or "")
        url = urljoin(self._base_url_str + "/", path)
        headers = {"User-Agent": self._ua} if self._ua else {}
        if method == "POST":
            body = sc.get("body") or {}
            res = RequestUtils(headers=headers, cookies=self._cookie if self._cookie else None,
                               proxies=self._proxies, timeout=30).post_res(url=url, data=json.dumps(body))
        else:
            res = self._fetch_html(url)
        if not res:
            return
        try:
            data = json.loads(res) if isinstance(res, str) else res
        except Exception:
            return
        total = 0
        total_size = 0
        info = []
        items_key = sc.get("response", {}).get("items_key", "data")
        size_field = sc.get("response", {}).get("size_field", "size")
        seeders_field = sc.get("response", {}).get("seeders_field", "seeders")
        items = self._get_nested(data, items_key.split(".")) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        for item in items:
            if isinstance(item, dict):
                size = int(self._get_nested(item, size_field.split(".")) or 0)
                seeders = int(self._get_nested(item, seeders_field.split(".")) or 0)
            else:
                size = StringUtils.num_filesize(str(item))
                seeders = 0
            total += 1
            total_size += size
            info.append([seeders, size])
        self.seeding_size = total_size
        self.seeding_info = json.dumps(info)

    @staticmethod
    def _get_nested(obj, keys):
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            elif isinstance(obj, list):
                try:
                    obj = obj[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return obj

    def _fetch_html(self, url, referer=None, use_ajax_headers=True):
        headers = dict(self._headers) if self._headers else {}
        headers.setdefault("User-Agent", self._ua)
        if use_ajax_headers:
            headers.update({
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            })
        else:
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            })
        if referer:
            headers["Referer"] = referer
        elif "Referer" not in headers and "referer" not in headers:
            headers.setdefault("Referer", self._base_url_str)
        res = RequestUtils(cookies=self._cookie if self._cookie else None,
                           session=self._session,
                           headers=headers, proxies=self._proxies,
                           timeout=30).get_res(url=url)
        if res and res.status_code == 200:
            res.encoding = res.apparent_encoding
            return res.text
        return None


def _html_config_factory(url, site_name, site_cookie, html_text=None,
                         site_headers=None, ua="", emulate=False, proxy=False, session=None):
    engine = SiteEngine.get_instance()
    site_def = engine.get_by_url(url)
    if not site_def:
        return None
    return ConfigHtmlUserInfo(site_def, site_name, url, site_cookie,
                              site_headers=site_headers, ua=ua, emulate=emulate,
                              proxy=proxy, session=session, json_data=html_text)


SiteEngine.get_instance().register_user_info_factory(_html_config_factory)
