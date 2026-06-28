__all__ = [
    "DEFAULT_SEARCH_DIR",
    "SORT_LABELS",
    "build_search_url",
    "collect_xiaohongshu",
    "normalize_feed_items",
    "find_chrome_executable",
]


def __getattr__(name):
    if name in __all__:
        from . import xiaohongshu_minimal

        return getattr(xiaohongshu_minimal, name)
    raise AttributeError(name)