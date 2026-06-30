import pytest

from app.data_sources import import_chanmama_file, run_data_source_import, scan_chanmama_pending


def test_import_chanmama_csv_builds_import_record(tmp_path):
    path = tmp_path / "videos.csv"
    path.write_text("video_id,title\nv1,hello\n", encoding="utf-8")

    record = import_chanmama_file(path)

    assert record["source"] == "chanmama"
    assert record["file_type"] == "csv"
    assert record["detected_entity_type"] == "video"
    assert record["record_count"] == 1
    assert record["status"] == "success"
    assert record["provenance"]["columns"] == ["title", "video_id"]


def test_import_chanmama_json_detects_product_records(tmp_path):
    path = tmp_path / "products.json"
    path.write_text('{"records":[{"product_id":"p1","name":"cat food"}]}', encoding="utf-8")

    record = import_chanmama_file(path)

    assert record["detected_entity_type"] == "product"
    assert record["record_count"] == 1


def test_scan_chanmama_pending_moves_success_and_failed_files(tmp_path):
    root = tmp_path / "watched_imports" / "chanmama"
    pending = root / "pending"
    pending.mkdir(parents=True)
    (pending / "ok.csv").write_text("creator_id,name\nc1,A\n", encoding="utf-8")
    (pending / "bad.txt").write_text("nope", encoding="utf-8")

    records = scan_chanmama_pending(root)

    assert [record["status"] for record in records] == ["failed", "success"]
    assert (root / "processed" / "ok.csv").exists()
    assert (root / "failed" / "bad.txt").exists()
    assert not (pending / "ok.csv").exists()
    assert not (pending / "bad.txt").exists()


def test_data_source_hub_summarizes_chanmama_import(tmp_path):
    root = tmp_path / "watched_imports" / "chanmama"
    pending = root / "pending"
    pending.mkdir(parents=True)
    (pending / "ok.csv").write_text("brand_id,name\nb1,Brand\n", encoding="utf-8")

    summary = run_data_source_import("chanmama", path=root)

    assert summary["source"] == "chanmama"
    assert summary["record_count"] == 1
    assert summary["records"][0]["detected_entity_type"] == "brand"
    assert summary["provenance"][0]["source_type"] == "chanmama_export"


def test_data_source_hub_rejects_unknown_source():
    with pytest.raises(ValueError, match="unsupported data source"):
        run_data_source_import("unknown")
