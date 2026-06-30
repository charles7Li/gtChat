__all__ = [
    "DEFAULT_SEARCH_DIR",
    "SORT_LABELS",
    "build_search_url",
    "check_douyin_login",
    "collect_xiaohongshu",
    "collect_douyin_hot_board",
    "collect_douyin_search",
    "douyin_hot_item_to_signal",
    "get_douyin_detail",
    "import_douyin_official_keywords",
    "normalize_feed_items",
    "normalize_douyin_content_item",
    "normalize_douyin_hot_item",
    "normalize_douyin_image_text_item",
    "normalize_douyin_item",
    "official_keyword_to_signal",
    "find_chrome_executable",
]


def __getattr__(name):
    if name in {
        "check_douyin_login",
        "collect_douyin_hot_board",
        "collect_douyin_search",
        "douyin_hot_item_to_signal",
        "get_douyin_detail",
        "import_douyin_official_keywords",
        "normalize_douyin_content_item",
        "normalize_douyin_hot_item",
        "normalize_douyin_image_text_item",
        "normalize_douyin_item",
        "official_keyword_to_signal",
    }:
        from . import douyin_minimal

        return getattr(douyin_minimal, name)
    if name in __all__:
        from . import xiaohongshu_minimal

        return getattr(xiaohongshu_minimal, name)
    raise AttributeError(name)
