from datetime import date
from unittest.mock import patch

import pytest

import main
from models import Transaction, ParseResult

FAKECOIN = (
    "Date,Amount,Currency,Type,Status,Merchant,Card Last Four,"
    "Reward Amount,Reward Currency,Reward Status,Reward Rate\n"
    "2026-06-01,12.50,USD,PURCHASE,SETTLED,WHOLE FOODS,1234,0,USD,NONE,0\n"
)


@pytest.fixture
def csv_file(tmp_path):
    f = tmp_path / "Fakecoin Card.csv"
    f.write_text(FAKECOIN)
    return f


def _run(args, existing_rows=None, log_path=None):
    with patch("main.read_existing_rows", return_value=existing_rows if existing_rows is not None else []) as rd, \
         patch("main.append_transactions", return_value=0) as wr, \
         patch("main.import_log.LOG_PATH", log_path), \
         patch("main.CREDENTIALS_FILE_EXISTS", True):
        main.run(main.parse_args(args))
    return rd, wr


def test_appends_new_rows(csv_file, tmp_path):
    rd, wr = _run([str(csv_file)], log_path=tmp_path / "log.json")
    wr.assert_called_once()
    appended = wr.call_args[0][0]
    assert len(appended) == 1
    assert appended[0].source_file == "Fakecoin Card.csv"
    assert appended[0].account == "Fakecoin Card"


def test_dedup_against_existing_sheet(csv_file, tmp_path):
    existing = [["06/01/2026", "12.50", "WHOLE FOODS", "", True, "", "Fakecoin Card"]]
    rd, wr = _run([str(csv_file)], existing_rows=existing, log_path=tmp_path / "log.json")
    wr.assert_not_called()


def test_skip_if_already_imported(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    _run([str(csv_file)], log_path=log_path)
    rd, wr = _run([str(csv_file)], log_path=log_path)
    wr.assert_not_called()


def test_force_reprocesses_logged_file(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    _run([str(csv_file)], log_path=log_path)
    rd, wr = _run([str(csv_file), "--force"], log_path=log_path)
    wr.assert_called_once()


def test_dry_run_writes_nothing(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    rd, wr = _run([str(csv_file), "--dry-run"], log_path=log_path)
    wr.assert_not_called()
    assert not log_path.exists()


def test_missing_path_errors():
    with pytest.raises(SystemExit):
        main.run(main.parse_args(["/no/such/file.csv"]))


def test_date_filter_excludes_out_of_window(csv_file, tmp_path):
    # The only row is dated 2026-06-01; a --from in July excludes it.
    rd, wr = _run([str(csv_file), "--from", "2026-07-01"], log_path=tmp_path / "log.json")
    wr.assert_not_called()


def test_bad_date_arg_exits(csv_file, tmp_path):
    with pytest.raises(SystemExit):
        _run([str(csv_file), "--to", "garbage"], log_path=tmp_path / "log.json")


def test_no_credentials_skips_dedup_but_appends(csv_file, tmp_path):
    with patch("main.read_existing_rows") as rd, \
         patch("main.append_transactions", return_value=0) as wr, \
         patch("main.import_log.LOG_PATH", tmp_path / "log.json"), \
         patch("main.CREDENTIALS_FILE_EXISTS", False):
        main.run(main.parse_args([str(csv_file)]))
    rd.assert_not_called()          # dedup skipped without credentials
    wr.assert_called_once()         # rows still appended (parse-only)


def test_unmatched_csv_exits_with_filename(tmp_path):
    bad = tmp_path / "Mystery.csv"
    bad.write_text("Foo,Bar\n1,2\n")
    with pytest.raises(SystemExit) as exc:
        _run([str(bad)], log_path=tmp_path / "log.json")
    assert "Mystery.csv" in str(exc.value)
