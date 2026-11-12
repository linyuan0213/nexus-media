"""ApiSiteSearcher 请求体处理测试"""

from unittest.mock import MagicMock, patch

from app.sites.search.api_searcher import ApiSiteSearcher


class TestStripEmptyLists:
    """空数组参数（categories: []）发送前剔除——避免部分 API 对显式空数组返回 500"""

    def _searcher(self) -> ApiSiteSearcher:
        site = MagicMock()
        site.domain = "x.example.com"
        site.api.base_url = "https://x.example.com"
        site.api.auth = {"type": "api_key", "header_name": "x-api-key", "user_agent": ""}
        site.api.endpoints = {"search": {"method": "POST", "path": "/search", "body": {}}}
        site.name = "TestAPI"
        engine = MagicMock()
        engine._build_headers.return_value = {"x-api-key": "k"}
        return ApiSiteSearcher(site, engine, {"api_key": "k"})

    def test_empty_categories_omitted(self):
        s = self._searcher()
        with patch("app.sites.search.api_searcher.HttpClient") as client_cls:
            client_cls.return_value.post.return_value.is_success = True
            client_cls.return_value.post.return_value.json.return_value = {"data": []}
            s._execute_request(
                {"method": "POST", "path": "/search", "content_type": "application/json"},
                {"keyword": "", "categories": [], "visible": 1},
                {"keyword": "", "page": "0"},
            )
        kwargs = client_cls.return_value.post.call_args.kwargs
        body = kwargs["data"]
        assert "categories" not in body
        assert "keyword" in body

    def test_api_error_response_sets_last_error(self):
        s = self._searcher()
        with patch("app.sites.search.api_searcher.HttpClient") as client_cls:
            client_cls.return_value.post.return_value.is_success = True
            client_cls.return_value.post.return_value.json.return_value = {
                "code": "4",
                "data": None,
                "message": "請求過於頻繁",
            }
            result = s._execute_request(
                {"method": "POST", "path": "/search", "content_type": "application/json"},
                {"keyword": "IPTD-543"},
                {"keyword": "IPTD-543", "page": "0"},
            )
        assert result == []
        assert s.last_error == "API 4: 請求過於頻繁"

    def test_nonempty_categories_kept(self):
        s = self._searcher()
        with patch("app.sites.search.api_searcher.HttpClient") as client_cls:
            client_cls.return_value.post.return_value.is_success = True
            client_cls.return_value.post.return_value.json.return_value = {"data": []}
            s._execute_request(
                {"method": "POST", "path": "/search", "content_type": "application/json"},
                {"keyword": "Lost", "categories": [401], "visible": 1},
                {"keyword": "Lost", "page": "0"},
            )
        kwargs = client_cls.return_value.post.call_args.kwargs
        body = kwargs["data"]
        assert '"categories":[401]' in body


class TestApplyPageSize:
    """每页数量按站点实际参数名覆盖（page_size/pageSize/size/嵌套 pageParam/params）"""

    def test_hddolby_page_size(self):
        body = {"page_number": 0, "page_size": 100}
        ApiSiteSearcher._apply_page_size(body, 20)
        assert body["page_size"] == 20

    def test_mteam_camelcase_pageSize(self):
        body = {"pageNumber": 1, "pageSize": 100}
        ApiSiteSearcher._apply_page_size(body, 50)
        assert body["pageSize"] == 50
        assert "page_size" not in body

    def test_tnode_size(self):
        body = {"page": 1, "size": 20}
        ApiSiteSearcher._apply_page_size(body, 50)
        assert body["size"] == 50

    def test_yemapt_nested_pageParam(self):
        body = {"pageParam": {"current": 1, "pageSize": 20}}
        ApiSiteSearcher._apply_page_size(body, 40)
        assert body["pageParam"]["pageSize"] == 40

    def test_no_page_param_untouched(self):
        body = {"keyword": "x"}
        ApiSiteSearcher._apply_page_size(body, 20)
        assert "page_size" not in body

    def test_none_page_size_untouched(self):
        body = {"page_size": 100}
        ApiSiteSearcher._apply_page_size(body, None)
        assert body["page_size"] == 100


class TestPostQueryParams:
    """POST 搜索也支持 query string（如 Piggo 的 q/page）"""

    def _searcher(self) -> ApiSiteSearcher:
        site = MagicMock()
        site.domain = "x.example.com"
        site.api.base_url = "https://api.x.example.com"
        site.api.auth = {"type": "api_key", "header_name": "x-api-key"}
        site.api.endpoints = {"search": {"method": "POST", "path": "/search"}}
        site.name = "TestAPI"
        engine = MagicMock()
        engine._build_headers.return_value = {"x-api-key": "k"}
        return ApiSiteSearcher(site, engine, {"api_key": "k"})

    def test_post_params_become_query_string(self):
        s = self._searcher()
        with patch("app.sites.search.api_searcher.HttpClient") as client_cls:
            client_cls.return_value.post.return_value.is_success = True
            client_cls.return_value.post.return_value.json.return_value = {"data": []}
            s._execute_request(
                {
                    "method": "POST",
                    "path": "/search",
                    "params": {"q": "{keyword}", "page": "{page_1}"},
                    "body": {},
                },
                {},
                {"keyword": "沙丘", "page": "0", "page_1": "1"},
            )
        url = client_cls.return_value.post.call_args.kwargs["url"]
        assert "q=%E6%B2%99%E4%B8%98" in url
        assert "page=1" in url
        assert client_cls.return_value.post.call_args.kwargs["data"] == "{}"


class TestDottedDownloadResponse:
    def test_dotted_response_key(self):
        from app.sites.download.engine_download import _response_value

        assert _response_value({"data": {"url": "https://x/torrent"}}, "data.url") == "https://x/torrent"
        assert _response_value({"data": {"url": "https://x/torrent"}}, "data") == {"url": "https://x/torrent"}


class TestApiDownload:
    def test_download_api_reads_dotted_url(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.sites.download.engine_download import resolve_download_api

        site = SimpleNamespace(
            domain="piggo.me",
            api=SimpleNamespace(base_url="https://api.piggo.me"),
            download=SimpleNamespace(method="POST", body={}, response_key="data.url", presigned=True),
        )
        engine = MagicMock()
        engine._build_auth.return_value = ({}, None)
        engine.site_limiter = None
        with patch("app.sites.download.engine_download.HttpClient") as client_cls:
            client_cls.return_value.post.return_value.json.return_value = {
                "data": {"url": "https://piggo.me/v1/web/torrents/1/dl/x"}
            }
            result = resolve_download_api(
                engine,
                "https://api.piggo.me/v1/api/torrents/1/download-link",
                site,
                {"bearer_token": "token"},
                "1",
            )
        assert result == "https://piggo.me/v1/web/torrents/1/dl/x"
        assert client_cls.return_value.post.call_args.kwargs["url"].endswith("/download-link")


class TestLabelsMapping:
    def test_labels_from_category_ids_and_text(self):
        s = ApiSiteSearcher.__new__(ApiSiteSearcher)
        cfg = {
            "type": "labels",
            "sources": [{"source": "category_ids", "map": {"6": "动画", "15": "冒险"}}],
            "text": "name",
            "text_tags": {"4K|2160p": "4K"},
        }
        item = {"category_ids": [6, 15], "name": "Demo 2160p WEB-DL"}
        assert s._map_field(item, cfg) == "动画|冒险|4K"


class TestFullPiggoFields:
    def test_full_tags_and_promotion_map(self):
        s = ApiSiteSearcher.__new__(ApiSiteSearcher)
        labels_cfg = {
            "type": "labels",
            "sources": [
                {"source": "categories", "key": "name"},
                {"source": "taxonomies", "key": "name"},
                {"source": "tags", "key": "name"},
                {"source": "promotion.label"},
                {"source": "category_ids", "map": {"6": "动画"}},
            ],
            "text": "name",
            "text_tags": {"4K|2160p": "4K"},
        }
        item = {
            "name": "Demo 2160p",
            "categories": [{"id": 6, "name": "动画"}, {"id": 15, "name": "冒险"}],
            "taxonomies": [{"id": 11, "name": "4K"}],
            "tags": [{"id": 3, "name": "国语"}, {"id": 2, "name": "禁转"}],
            "promotion": {"label": "免费", "up": 1, "down": 0},
            "category_ids": [6],
        }
        assert s._map_field(item, labels_cfg) == "动画|冒险|4K|国语|禁转|免费"
        assert s._map_field(item, {"type": "mapping", "source": "promotion.down", "map": {"0": 0.0, "0.5": 0.5}}) == 0.0
        up_cfg = {"type": "mapping", "source": "promotion.up", "map": {"2": 2.0}}
        assert s._map_field({"promotion": {"up": 2}}, up_cfg) == 2.0


class TestApiProfiles:
    def _site(self):
        from app.sites.config.site_definition import SiteDefinition

        return SiteDefinition.from_dict(
            {
                "id": "demo",
                "domain": "example.com",
                "api": {
                    "base_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token_key": "api_key"},
                    "endpoints": {"search": {"method": "GET", "path": "/search"}},
                    "default_profile": "official",
                    "profiles": {
                        "official": {
                            "base_url": "https://api.example.com",
                            "auth": {"type": "bearer", "token_key": "api_key"},
                            "endpoints": {"search": {"method": "GET", "path": "/search"}},
                        },
                        "spa": {
                            "base_url": "https://example.com",
                            "auth": {"type": "bearer", "spa": {"signer": "piggo", "sign_path": "/sign"}},
                            "endpoints": {"search": {"method": "GET", "path": "/spa/search"}},
                        },
                    },
                    "capabilities": {"search": ["spa", "official"]},
                },
            }
        )

    def test_profile_resolution_skips_missing_credentials(self):
        from app.sites.config import site_profile

        site = self._site()
        user = {"note": {"api_credentials": {"official": {"api_key": "k"}}}}
        resolved = site_profile.resolve_api_profile(site, user, "search")
        assert resolved is not None
        name, api = resolved
        assert name == "official"
        assert api.base_url == "https://api.example.com"

    def test_profile_resolution_prefers_ready_spa(self):
        from app.sites.config import site_profile

        site = self._site()
        user = {
            "note": {
                "api_credentials": {
                    "official": {"api_key": "k"},
                    "spa": {"bearer_token": "jwt"},
                }
            }
        }
        resolved = site_profile.resolve_api_profile(site, user, "search")
        assert resolved is not None
        name, api = resolved
        assert name == "spa"
        assert api.base_url == "https://example.com"

    def test_spa_headers_use_sign_and_hmac(self):
        site = self._site()
        user = {"note": {"api_credentials": {"spa": {"bearer_token": "a" * 64}}}}
        searcher = ApiSiteSearcher(site, MagicMock(), user)
        client = MagicMock()
        client.get.return_value.is_success = True
        client.get.return_value.json.return_value = {"data": {"sign": "b" * 64}}
        from app.sites.http import spa_signer

        headers = spa_signer.spa_signed_headers(
            searcher,
            searcher._api,
            searcher._user_config,
            client,
            {"Authorization": "Bearer token"},
            "GET",
            "https://example.com/spa/search?q=x",
        )
        assert headers["X-Spa-Nonce"]
        assert len(headers["X-Spa-Hmac"]) == 64
        assert headers["version"] == "1.0.0"
        assert headers["webversion"] == "1"


class TestProfileFallbackSearch:
    def test_fallback_rebuilds_request_from_each_profile(self, monkeypatch):
        from app.sites.config.site_definition import SiteDefinition

        site = SiteDefinition.from_dict(
            {
                "id": "demo",
                "domain": "example.com",
                "api": {
                    "base_url": "https://api.example.com",
                    "auth": {"type": "bearer"},
                    "endpoints": {"search": {"method": "GET", "path": "/search"}},
                    "default_profile": "official",
                    "profiles": {
                        "spa": {
                            "base_url": "https://example.com",
                            "auth": {"type": "bearer", "token_key": "bearer_token"},
                            "endpoints": {
                                "search": {
                                    "method": "GET",
                                    "path": "/spa",
                                    "body": {"q": "{keyword}"},
                                }
                            },
                        },
                        "official": {
                            "base_url": "https://api.example.com",
                            "auth": {"type": "bearer", "token_key": "api_key"},
                            "endpoints": {
                                "search": {
                                    "method": "GET",
                                    "path": "/search",
                                    "body": {"keyword": "{keyword}"},
                                }
                            },
                        },
                    },
                    "capabilities": {"search": ["spa", "official"]},
                },
            }
        )
        user = {
            "note": {
                "api_credentials": {
                    "spa": {"bearer_token": "spa-token"},
                    "official": {"api_key": "official-token"},
                }
            }
        }
        searcher = ApiSiteSearcher(site, MagicMock(), user)
        calls: list[dict] = []

        def fake_execute(config, body, template_vars, page_size=None):
            calls.append(dict(body))
            if len(calls) == 1:
                searcher.last_error = "HTTP 401"
                return []
            return [{"title": "fallback"}]

        monkeypatch.setattr(searcher, "_execute_request", fake_execute)
        result = searcher.search("demo")
        assert result == [{"title": "fallback"}]
        assert calls[0] == {"q": "demo"}
        assert calls[1] == {"keyword": "demo"}
        assert searcher._profile_name == "official"


class TestSpaDownload:
    def test_spa_download_posts_json_and_returns_url(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.sites.download.engine_download import resolve_download_api

        download = SimpleNamespace(
            type="api",
            method="POST",
            body={},
            response_key="data.url",
            presigned=True,
            path="/v1/web/torrents/{tid}/download-link",
        )
        api = SimpleNamespace(
            base_url="https://piggo.me",
            http2=True,
            auth={"type": "bearer", "spa": {"sign_path": "/sign"}},
            download=download,
        )
        site = SimpleNamespace(domain="piggo.me", download=download, api=api)
        engine = MagicMock()
        engine._build_auth.return_value = ({}, None)
        engine.site_limiter = None
        with (
            patch("app.sites.download.engine_download.HttpClient") as client_cls,
            patch("app.sites.download.engine_download.spa_signer.spa_signed_headers", return_value={"X-Spa-Hmac": "x"}),
        ):
            client = client_cls.return_value
            client.post.return_value.json.return_value = {"data": {"url": "https://piggo.me/dl/1"}}
            result = resolve_download_api(
                engine,
                "https://piggo.me/v1/web/torrents/1/download-link",
                site,
                {"note": {"api_credentials": {"spa": {"bearer_token": "jwt"}}}},
                "1",
                api=api,
            )
        assert result == "https://piggo.me/dl/1"
        assert client.post.call_args.kwargs.get("json") == {}


class TestDownloadProfileFallback:
    def test_download_tries_next_profile(self, monkeypatch):
        from app.sites.engine import SiteEngine

        engine = SiteEngine(definitions_dir="config/sites")
        calls = []

        def fake_download(*args, **kwargs):
            calls.append(args[2].download.path)
            return None if len(calls) == 1 else "https://piggo.me/dl/1"

        monkeypatch.setattr(
            "app.sites.engine.engine_download.resolve_download_api",
            fake_download,
        )
        result = engine.resolve_download_url(
            "https://piggo.me/detail/57230",
            {"note": {"api_credentials": {"spa": {"bearer_token": "jwt"}, "official": {"api_key": "key"}}}},
        )
        assert result == "https://piggo.me/dl/1"
        assert len(calls) == 2
