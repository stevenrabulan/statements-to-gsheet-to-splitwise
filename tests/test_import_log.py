from datetime import datetime

import pytest

import import_log


def test_file_hash_is_content_based(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("hello")
    h1 = import_log.file_hash(f)
    f.write_text("hello world")
    assert import_log.file_hash(f) != h1


def test_append_then_load_roundtrip(tmp_path):
    log_path = tmp_path / "import_log.json"
    entry = {"file": "a.csv", "sha256": "abc", "account": "Visa",
             "source": "fakecoin", "imported_at": datetime.now().isoformat(),
             "rows_new": 3, "rows_skipped": 1, "date_range": ["2026-06-01", "2026-06-30"]}
    import_log.append_entry(entry, path=log_path)
    log = import_log.load_log(log_path)
    assert len(log) == 1 and log[0]["sha256"] == "abc"


def test_find_by_hash(tmp_path):
    log_path = tmp_path / "import_log.json"
    import_log.append_entry({"sha256": "abc"}, path=log_path)
    log = import_log.load_log(log_path)
    assert import_log.find_by_hash("abc", log)["sha256"] == "abc"
    assert import_log.find_by_hash("nope", log) is None


def test_missing_log_is_empty(tmp_path):
    assert import_log.load_log(tmp_path / "nope.json") == []


def test_corrupt_log_starts_fresh(tmp_path, capsys):
    log_path = tmp_path / "import_log.json"
    log_path.write_text("{ not json")
    assert import_log.load_log(log_path) == []
    assert "corrupt" in capsys.readouterr().out.lower()
