from datetime import date
from unittest.mock import patch

import pytest

import main
from models import AccountConfig, Transaction, ParseResult

FAKECOIN = (
    "Date,Amount,Currency,Type,Status,Merchant,Card Last Four,"
    "Reward Amount,Reward Currency,Reward Status,Reward Rate\n"
    "2026-06-01,12.50,USD,PURCHASE,SETTLED,WHOLE FOODS,1234,0,USD,NONE,0\n"
)

# FakeMart exports full card history, so rows straddle the ignore_before cutoff.
FakeMart = (
    "Date,Amount,Type,Merchant,Category,Method\n"
    '"2026/05/20, 09:01:00",10.00,transaction,FakeMart OLD,Groceries,Card\n'
    '"2026/06/22, 15:13:12",25.00,transaction,FakeMart NEW,Groceries,Card\n'
)


@pytest.fixture
def csv_file(tmp_path):
    f = tmp_path / "Fakecoin Card.csv"
    f.write_text(FAKECOIN)
    return f


@pytest.fixture
def fakemart_file(tmp_path):
    f = tmp_path / "FakeMart Credit Card.csv"
    f.write_text(FakeMart)
    return f


CHASE_HEADER = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"


def _chase_file(tmp_path, lines):
    f = tmp_path / "Chase Amazon.csv"
    f.write_text(CHASE_HEADER + "".join(f"{line}\n" for line in lines))
    return f


def _run_chase(chase_file, tmp_path):
    return _run([str(chase_file)], log_path=tmp_path / "log.json",
                accounts_map={"Chase Amazon": AccountConfig("Amazon Card")})


def _run(args, existing_rows=None, log_path=None, accounts_map=None):
    if accounts_map is None:
        accounts_map = {"Fakecoin": AccountConfig("Fakecoin Card")}
    with patch("main.read_existing_rows", return_value=existing_rows if existing_rows is not None else []) as rd, \
         patch("main.append_transactions", return_value=(1, 2, 2)) as wr, \
         patch("main.import_log.LOG_PATH", log_path), \
         patch("main.CREDENTIALS_FILE_EXISTS", True), \
         patch("main.accounts.load_accounts", return_value=accounts_map):
        main.run(main.parse_args(args))
    return rd, wr


def test_appends_new_rows(csv_file, tmp_path):
    rd, wr = _run([str(csv_file)], log_path=tmp_path / "log.json")
    wr.assert_called_once()
    appended = wr.call_args[0][0]
    assert len(appended) == 1
    assert appended[0].source_file == f"{csv_file.parent.name}/Fakecoin Card.csv"
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
         patch("main.append_transactions", return_value=(1, 2, 2)) as wr, \
         patch("main.import_log.LOG_PATH", tmp_path / "log.json"), \
         patch("main.CREDENTIALS_FILE_EXISTS", False), \
         patch("main.accounts.load_accounts", return_value={"Fakecoin": AccountConfig("Fakecoin Card")}):
        main.run(main.parse_args([str(csv_file)]))
    rd.assert_not_called()          # dedup skipped without credentials
    wr.assert_called_once()         # rows still appended (parse-only)


def test_unmatched_csv_exits_with_filename(tmp_path):
    bad = tmp_path / "Mystery.csv"
    bad.write_text("Foo,Bar\n1,2\n")
    with pytest.raises(SystemExit) as exc:
        _run([str(bad)], log_path=tmp_path / "log.json",
             accounts_map={"Mystery": AccountConfig("Mystery Acct")})
    assert "Mystery.csv" in str(exc.value)


def test_no_account_match_exits(tmp_path):
    f = tmp_path / "Unknown1234.csv"
    f.write_text(FAKECOIN)
    with pytest.raises(SystemExit) as exc:
        _run([str(f)], log_path=tmp_path / "log.json",
             accounts_map={"Fakecoin": AccountConfig("Fakecoin Card")})
    assert "Unknown1234.csv" in str(exc.value)


def _fakemart_map(cutoff):
    return {"FakeMart": AccountConfig("FakeMart Card", cutoff)}


def test_ignore_before_drops_older_rows(fakemart_file, tmp_path):
    rd, wr = _run([str(fakemart_file)], log_path=tmp_path / "log.json",
                  accounts_map=_fakemart_map(date(2026, 6, 1)))
    appended = wr.call_args[0][0]
    assert [t.description for t in appended] == ["FakeMart NEW"]


def test_ignore_before_keeps_row_on_the_cutoff_day(fakemart_file, tmp_path):
    """The cutoff is inclusive — a transaction dated exactly ignore_before is kept."""
    rd, wr = _run([str(fakemart_file)], log_path=tmp_path / "log.json",
                  accounts_map=_fakemart_map(date(2026, 5, 20)))
    appended = wr.call_args[0][0]
    assert [t.description for t in appended] == ["FakeMart OLD", "FakeMart NEW"]


def test_no_ignore_before_keeps_everything(fakemart_file, tmp_path):
    rd, wr = _run([str(fakemart_file)], log_path=tmp_path / "log.json",
                  accounts_map=_fakemart_map(None))
    assert len(wr.call_args[0][0]) == 2


def test_ignore_before_dropping_all_rows_writes_nothing(fakemart_file, tmp_path):
    rd, wr = _run([str(fakemart_file)], log_path=tmp_path / "log.json",
                  accounts_map=_fakemart_map(date(2027, 1, 1)))
    wr.assert_not_called()


def test_ignore_before_reported_as_skipped(fakemart_file, tmp_path, capsys):
    _run([str(fakemart_file)], log_path=tmp_path / "log.json",
         accounts_map=_fakemart_map(date(2026, 6, 1)))
    assert "before 2026-06-01" in capsys.readouterr().out


def test_account_override_keeps_matched_cutoff(fakemart_file, tmp_path):
    """--account relabels the rows but must not silently drop the cutoff."""
    rd, wr = _run([str(fakemart_file), "--account", "Other Label"], log_path=tmp_path / "log.json",
                  accounts_map=_fakemart_map(date(2026, 6, 1)))
    appended = wr.call_args[0][0]
    assert [(t.description, t.account) for t in appended] == [("FakeMart NEW", "Other Label")]


def test_account_override_without_match_has_no_cutoff(fakemart_file, tmp_path):
    rd, wr = _run([str(fakemart_file), "--account", "Other Label"], log_path=tmp_path / "log.json",
                  accounts_map={"Fakecoin": AccountConfig("Fakecoin Card")})
    assert len(wr.call_args[0][0]) == 2


def test_ignore_before_applies_before_date_range_log_entry(fakemart_file, tmp_path):
    """The logged date_range must reflect kept rows only."""
    import json
    log_path = tmp_path / "log.json"
    _run([str(fakemart_file)], log_path=log_path, accounts_map=_fakemart_map(date(2026, 6, 1)))
    entry = json.loads(log_path.read_text())[0]
    assert entry["date_range"] == ["2026-06-22", "2026-06-22"]
    assert entry["rows_skipped"] == 1


def test_amazon_order_charges_dropped_from_card_import(tmp_path, capsys):
    chase = _chase_file(tmp_path, [
        "09/01/2026,09/02/2026,Amazon.com*AB12C3DE4,Shopping,Sale,-23.10,",
        "09/02/2026,09/03/2026,AMAZON MKTPL*Y25EQ0CT3,Shopping,Sale,-11.93,",
        "09/03/2026,09/04/2026,amzn mktp us*ZZ9YY8XX7,Shopping,Sale,-38.28,",
        "09/04/2026,09/05/2026,AMAZON MKTPL*Q11RR22SS,Shopping,Return,5.00,",
        "09/05/2026,09/06/2026,WHOLEFDS AUS 10250,Groceries,Sale,-42.17,",
    ])
    _, wr = _run_chase(chase, tmp_path)
    appended = wr.call_args[0][0]
    assert [t.description for t in appended] == ["WHOLEFDS AUS 10250"]
    assert "'amazon order charge': 4" in capsys.readouterr().out


def test_non_order_amazon_charges_still_import(tmp_path):
    kept = ["Amazon Prime*AB1CD2EF3", "Prime Video *GH4IJ5KL6",
            "Kindle Svcs*MN7OP8QR9", "Audible*ST1UV2WX3", "WHOLEFDS AUS 10250"]
    chase = _chase_file(tmp_path, [f"09/01/2026,09/02/2026,{desc},Shopping,Sale,-9.99," for desc in kept])
    _, wr = _run_chase(chase, tmp_path)
    appended = wr.call_args[0][0]
    assert sorted(t.description for t in appended) == sorted(kept)
