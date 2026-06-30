import pytest

from app.collectors.douyin_minimal import (
    check_douyin_login,
    collect_douyin_hot_board,
    collect_douyin_search,
    douyin_hot_item_to_signal,
    get_douyin_detail,
    import_douyin_official_keywords,
    load_douyin_cookies,
    normalize_douyin_content_item,
    normalize_douyin_hot_item,
    normalize_douyin_image_text_item,
    normalize_douyin_item,
    official_keyword_to_signal,
    validate_douyin_live_config,
)


def test_check_douyin_login_requires_cookie_file(tmp_path):
    result = check_douyin_login(tmp_path / "missing.cookies.json")

    assert result["status"] == "auth_required"
    assert result["reason"] == "cookies_missing"


def test_load_douyin_cookies_reads_file(tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("[{\"name\":\"sessionid\",\"value\":\"abc\"}]", encoding="utf-8")

    assert load_douyin_cookies(cookie_path) == "[{\"name\":\"sessionid\",\"value\":\"abc\"}]"
    assert check_douyin_login(cookie_path)["status"] == "ok"


def test_normalize_douyin_item_handles_search_and_detail_shape():
    item = normalize_douyin_item(
        {
            "aweme_id": "729",
            "desc": "宠物避坑",
            "author": {"nickname": "阿橘"},
            "statistics": {"digg_count": 12000, "collect_count": 300, "comment_count": 45},
            "create_time": 1718000000,
            "text_extra": [],
            "hashtags": [{"name": "宠物"}, "避坑"],
        }
    )

    assert item["id"] == "729"
    assert item["title"] == "宠物避坑"
    assert item["author"] == "阿橘"
    assert item["liked_count"] == "12000"
    assert item["url"] == "https://www.douyin.com/video/729"
    assert item["tags"] == ["宠物", "避坑"]
    assert item["platform"] == "douyin"


def test_collect_douyin_search_dedupes_raw_items_without_network():
    items = collect_douyin_search(
        "pet",
        raw_items=[
            {"aweme_id": "1", "desc": "A"},
            {"aweme_id": "1", "desc": "A duplicate"},
            {"aweme_id": "2", "desc": "B"},
        ],
    )

    assert [item["id"] for item in items] == ["1", "2"]


def test_get_douyin_detail_normalizes_raw_item_without_network():
    item = get_douyin_detail("42", raw_item={"desc": "详情", "comment_count": 7})

    assert item["id"] == "42"
    assert item["comment_count"] == "7"


def test_normalize_douyin_hot_item_builds_trend_source():
    item = normalize_douyin_hot_item({"word": "今天养猫的人都在看", "sentence_id": "hot-1"}, 1)

    assert item["id"] == "douyin-hot-hot-1"
    assert item["type"] == "hot_trend"
    assert item["body_text"] == "抖音热榜：今天养猫的人都在看"


def test_collect_douyin_hot_board_normalizes_raw_items_without_network():
    items = collect_douyin_hot_board(raw_items=[{"word": "A"}, {"word": "B"}], limit=1)

    assert len(items) == 1
    assert items[0]["title"] == "A"


def test_normalize_douyin_image_text_item_builds_unified_content():
    item = normalize_douyin_image_text_item(
        {
            "aweme_id": "img-1",
            "desc": "image text post",
            "images": [{"url": "https://img.test/1.jpg"}, "https://img.test/2.jpg"],
            "author": {"nickname": "creator"},
            "statistics": {"digg_count": 5},
            "hashtags": ["tag-a"],
        },
        provenance={"source_type": "fixture"},
    )

    assert item["item_id"] == "img-1"
    assert item["source"] == "douyin"
    assert item["content_format"] == "image_text"
    assert item["images"] == ["https://img.test/1.jpg", "https://img.test/2.jpg"]
    assert item["metrics"]["liked_count"] == "5"
    assert item["provenance"]["source_type"] == "fixture"


def test_normalize_douyin_content_item_keeps_video_url():
    item = normalize_douyin_content_item({"aweme_id": "v1", "desc": "video", "video_url": "https://video.test/v1.mp4"})

    assert item["content_format"] == "video"
    assert item["video_url"] == "https://video.test/v1.mp4"


def test_douyin_hot_and_official_keywords_convert_to_signals():
    hot_signal = douyin_hot_item_to_signal({"word": "pet", "hot_value": "12.5", "rank": "2", "related_terms": "cat,dog"})
    keyword_signal = official_keyword_to_signal({"keyword": "cat food", "search_index": "99", "growth_rate": "0.4"})

    assert hot_signal["source"] == "douyin_hot_board"
    assert hot_signal["keyword"] == "pet"
    assert hot_signal["rank"] == 2
    assert hot_signal["heat_score"] == 12.5
    assert hot_signal["related_terms"] == ["cat", "dog"]
    assert keyword_signal["source"] == "douyin_official_keyword"
    assert keyword_signal["keyword"] == "cat food"
    assert keyword_signal["heat_score"] == 99.0


def test_import_douyin_official_keywords_from_json_and_csv(tmp_path):
    json_path = tmp_path / "keywords.json"
    csv_path = tmp_path / "keywords.csv"
    json_path.write_text('{"records":[{"keyword":"json keyword","search_index":10}]}', encoding="utf-8")
    csv_path.write_text("keyword,search_index\ncsv keyword,20\n", encoding="utf-8")

    json_signals = import_douyin_official_keywords(json_path)
    csv_signals = import_douyin_official_keywords(csv_path)

    assert json_signals[0]["keyword"] == "json keyword"
    assert json_signals[0]["provenance"]["path"] == str(json_path)
    assert csv_signals[0]["keyword"] == "csv keyword"
    assert csv_signals[0]["heat_score"] == 20.0


def test_live_search_requires_cookie_before_request(tmp_path):
    with pytest.raises(RuntimeError, match="Douyin auth required"):
        collect_douyin_search("pet", cookie_path=tmp_path / "missing.cookies.json")


def test_validate_douyin_live_config_reports_missing_endpoints(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("sessionid=abc", encoding="utf-8")
    monkeypatch.delenv("DOUYIN_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("DOUYIN_DETAIL_ENDPOINT", raising=False)
    monkeypatch.delenv("DOUYIN_HOT_BOARD_ENDPOINT", raising=False)

    result = validate_douyin_live_config(cookie_path)

    assert result["status"] == "not_ready"
    assert result["login"]["status"] == "ok"
    assert result["missing"] == ["DOUYIN_SEARCH_ENDPOINT", "DOUYIN_DETAIL_ENDPOINT", "DOUYIN_HOT_BOARD_ENDPOINT"]


def test_validate_douyin_live_config_ready(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("sessionid=abc", encoding="utf-8")
    monkeypatch.setenv("DOUYIN_SEARCH_ENDPOINT", "https://collector.test/search")
    monkeypatch.setenv("DOUYIN_DETAIL_ENDPOINT", "https://collector.test/detail")
    monkeypatch.setenv("DOUYIN_HOT_BOARD_ENDPOINT", "https://collector.test/hot")

    assert validate_douyin_live_config(cookie_path)["status"] == "ready"


def test_live_search_uses_configured_endpoint(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("[{\"name\":\"sessionid\",\"value\":\"abc\"}]", encoding="utf-8")
    monkeypatch.setenv("DOUYIN_SEARCH_ENDPOINT", "https://collector.test/search")
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"items":[{"aweme_id":"1","desc":"A"}]}'

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["cookie"] = req.headers["Cookie"]
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.collectors.douyin_minimal.request.urlopen", fake_urlopen)

    items = collect_douyin_search("pet", limit=3, cookie_path=cookie_path)

    assert items[0]["id"] == "1"
    assert "keyword=pet" in seen["url"]
    assert "limit=3" in seen["url"]
    assert seen["cookie"] == "sessionid=abc"
    assert seen["timeout"] == 20


def test_live_detail_and_hot_board_use_configured_endpoints(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("sessionid=abc", encoding="utf-8")
    monkeypatch.setenv("DOUYIN_DETAIL_ENDPOINT", "https://collector.test/detail")
    monkeypatch.setenv("DOUYIN_HOT_BOARD_ENDPOINT", "https://collector.test/hot")
    seen = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self.body

    def fake_urlopen(req, timeout):
        seen.append(req.full_url)
        if "/detail" in req.full_url:
            return FakeResponse(b'{"aweme_detail":{"desc":"detail","comment_count":9}}')
        return FakeResponse(b'{"word_list":[{"word":"hot"}]}')

    monkeypatch.setattr("app.collectors.douyin_minimal.request.urlopen", fake_urlopen)

    detail = get_douyin_detail("42", cookie_path=cookie_path)
    hot_items = collect_douyin_hot_board(limit=1, cookie_path=cookie_path)

    assert detail["id"] == "42"
    assert detail["comment_count"] == "9"
    assert hot_items[0]["title"] == "hot"
    assert any("aweme_id=42" in url for url in seen)
    assert any("limit=1" in url for url in seen)
