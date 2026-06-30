from app.live_checks import run_live_checks


def test_live_checks_default_to_dry_run(monkeypatch, tmp_path):
    cookie_path = tmp_path / "missing.cookies.json"
    monkeypatch.delenv("NOTIFICATION_WEBHOOK_URL", raising=False)

    result = run_live_checks(cookie_path=cookie_path)

    assert result["mode"] == "dry_run"
    assert result["checks"]["douyin"]["status"] == "not_ready"
    assert result["checks"]["notification"]["status"] == "not_ready"
    assert result["live_results"] == {}


def test_live_checks_allow_live_calls_ready_integrations(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("sessionid=abc", encoding="utf-8")
    monkeypatch.setenv("DOUYIN_SEARCH_ENDPOINT", "https://collector.test/search")
    monkeypatch.setenv("DOUYIN_DETAIL_ENDPOINT", "https://collector.test/detail")
    monkeypatch.setenv("DOUYIN_HOT_BOARD_ENDPOINT", "https://collector.test/hot")
    monkeypatch.setenv("NOTIFICATION_WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.setattr("app.live_checks.collect_douyin_search", lambda *args, **kwargs: [{"id": "1"}])
    monkeypatch.setattr("app.live_checks.get_douyin_detail", lambda *args, **kwargs: {"id": "1"})
    monkeypatch.setattr("app.live_checks.collect_douyin_hot_board", lambda *args, **kwargs: [{"id": "hot"}])
    monkeypatch.setattr("app.live_checks.send_notification", lambda *args, **kwargs: {"status": "sent"})

    result = run_live_checks(allow_live=True, cookie_path=cookie_path, limit=1)

    assert result["mode"] == "live"
    assert result["live_results"]["douyin_search"] == {"status": "ok", "count": 1}
    assert result["live_results"]["douyin_detail"] == {"status": "ok", "id": "1"}
    assert result["live_results"]["douyin_hot_board"] == {"status": "ok", "count": 1}
    assert result["live_results"]["notification"] == {"status": "sent"}


def test_live_checks_skips_detail_when_search_has_no_id(monkeypatch, tmp_path):
    cookie_path = tmp_path / "default.cookies.json"
    cookie_path.write_text("sessionid=abc", encoding="utf-8")
    monkeypatch.setenv("DOUYIN_SEARCH_ENDPOINT", "https://collector.test/search")
    monkeypatch.setenv("DOUYIN_DETAIL_ENDPOINT", "https://collector.test/detail")
    monkeypatch.setenv("DOUYIN_HOT_BOARD_ENDPOINT", "https://collector.test/hot")
    monkeypatch.delenv("NOTIFICATION_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("app.live_checks.collect_douyin_search", lambda *args, **kwargs: [{}])
    monkeypatch.setattr("app.live_checks.collect_douyin_hot_board", lambda *args, **kwargs: [])

    result = run_live_checks(allow_live=True, cookie_path=cookie_path)

    assert result["live_results"]["douyin_detail"] == {"status": "skipped", "reason": "search_returned_no_id"}
