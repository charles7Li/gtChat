from app.collectors.xiaohongshu_minimal import (
    build_search_url,
    normalize_feed_items,
    resolve_sort_label,
    resolve_time_label,
)


def test_build_search_url_encodes_keyword():
    url = build_search_url("宠物 避坑")
    assert "keyword=%E5%AE%A0%E7%89%A9%20%E9%81%BF%E5%9D%91" in url
    assert url.startswith("https://www.xiaohongshu.com/search_result?")


def test_resolve_filter_labels():
    assert resolve_sort_label("latest") == "最新"
    assert resolve_sort_label("popularity_descending") == "最多点赞"
    assert resolve_time_label("week") == "一周内"


def test_normalize_feed_items_builds_tokenized_url_and_dedupes():
    rows = normalize_feed_items(
        [
            {
                "id": "68e90be80000000004022e66",
                "xsecToken": "token",
                "title": "A",
                "author": "u",
                "liked_count": "12",
            },
            {"id": "68e90be80000000004022e66", "title": "A duplicate"},
            {"id": "x", "title": ""},
        ],
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["url"] == "https://www.xiaohongshu.com/explore/68e90be80000000004022e66?xsec_token=token&xsec_source=pc_search"
    assert rows[0]["liked_count"] == "12"
