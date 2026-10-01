import json
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import main
from models import AccountConfig, Transaction, ParseResult
from sheets_writer import build_row

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


AMAZON_FIXTURE = Path(__file__).parent / "fixtures" / "amazon-orders-sample.json"
AMAZON_ACCOUNTS = {
    "Fakecoin": AccountConfig("Fakecoin Card"),
    "Chase4242": AccountConfig("Amazon Card"),
    "amazon-orders": AccountConfig("Amazon", date(2026, 7, 29)),
}
AMAZON_NOTE = "split-transactions automation amazon 111-0000000-0000001 #1"


@pytest.fixture
def amazon_month(tmp_path):
    """A month folder holding a card CSV and a scraped Amazon Order file."""
    month = tmp_path / "2026-09"
    month.mkdir()
    (month / "Fakecoin Card.csv").write_text(FAKECOIN)
    shutil.copy(AMAZON_FIXTURE, month / "amazon-orders-2026-09-28.json")
    return month


def _sheet_rows(wr):
    return [build_row(t) for t in wr.call_args[0][0]]


def test_folder_with_amazon_file_writes_item_row(amazon_month, tmp_path):
    rd, wr = _run([str(amazon_month)], log_path=tmp_path / "log.json",
                  accounts_map=AMAZON_ACCOUNTS)
    rows = {row[2]: row for row in _sheet_rows(wr)}
    assert set(rows) == {"WHOLE FOODS", "Fakebrand ForceFlex Trash Bags"}
    item = rows["Fakebrand ForceFlex Trash Bags"]
    assert item[0] == "08/03/2026"
    assert item[1] == "=12.99+1.08"
    assert item[4] is True                  # Shared by default, like card rows
    assert item[6] == "Amazon Card"
    assert item[7] is None                  # For who left for the sheet to fill
    assert item[10] == AMAZON_NOTE
    # Card rows are unchanged.
    assert rows["WHOLE FOODS"][1] == 12.50
    assert rows["WHOLE FOODS"][10] == "split-transactions automation 2026-09/Fakecoin Card.csv"


def test_rescrape_of_imported_item_writes_nothing_even_if_amount_moved(amazon_month, tmp_path):
    existing = [
        ["06/01/2026", 12.50, "WHOLE FOODS", "", True, "", "Fakecoin Card", "", "", "", ""],
        # Same Order, already in the sheet, a cent off and renamed by hand.
        [46237, 14.08, "Trash bags", "", False, "Partner", "Amazon Card", "", "", "",
         AMAZON_NOTE],
    ]
    rd, wr = _run([str(amazon_month)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


def test_amazon_key_match_is_exact_not_a_prefix(amazon_month, tmp_path):
    # Item #10's key contains "#1" as a prefix; it must not hide Item #1.
    existing = [[46237, 5.00, "Other", "", True, "", "Amazon Card", "", "", "",
                 "split-transactions automation amazon 111-0000000-0000001 #10"]]
    rd, wr = _run([str(amazon_month / "amazon-orders-2026-09-28.json")], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [AMAZON_NOTE]


def test_amazon_dry_run_writes_nothing(amazon_month, tmp_path):
    log_path = tmp_path / "log.json"
    rd, wr = _run([str(amazon_month), "--dry-run"], log_path=log_path,
                  accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    assert not log_path.exists()


def test_amazon_file_is_logged_and_skipped_next_time(amazon_month, tmp_path):
    log_path = tmp_path / "log.json"
    amazon_file = str(amazon_month / "amazon-orders-2026-09-28.json")
    _run([amazon_file], log_path=log_path, accounts_map=AMAZON_ACCOUNTS)
    rd, wr = _run([amazon_file], log_path=log_path, accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    rd, wr = _run([amazon_file, "--force"], log_path=log_path, accounts_map=AMAZON_ACCOUNTS)
    wr.assert_called_once()


def test_date_range_filters_amazon_rows_by_order_date(amazon_month, tmp_path):
    rd, wr = _run([str(amazon_month / "amazon-orders-2026-09-28.json"), "--from", "2026-08-04"],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


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


def test_generic_cutoff_is_not_applied_again_to_amazon_rows(amazon_month, tmp_path):
    # Order placed 2026-07-25 (before the cutoff), shipped 2026-08-04 (after): still imported.
    src = json.loads(AMAZON_FIXTURE.read_text())
    src["orders"][0]["order_date"] = "2026-07-25"
    (amazon_month / "amazon-orders-2026-09-28.json").write_text(json.dumps(src))
    rd, wr = _run([str(amazon_month / "amazon-orders-2026-09-28.json")],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [AMAZON_NOTE]


def test_amazon_item_shipped_before_cutoff_is_dropped_once_and_counted(amazon_month, tmp_path, capsys):
    src = json.loads(AMAZON_FIXTURE.read_text())
    src["orders"][0]["shipments"][0]["ship_date"] = "2026-07-20"
    f = amazon_month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps(src))
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    assert "'before 2026-07-29': 1" in capsys.readouterr().out


AMAZON_REFUND_NOTE = f"{AMAZON_NOTE} refund 2026-08-20 12.99"


def _amazon_file_with_refund(month):
    src = json.loads(AMAZON_FIXTURE.read_text())
    src["refunds"] = [{"order_number": "111-0000000-0000001", "positions": [1],
                       "amount": 12.99, "refund_date": "2026-08-20"}]
    f = month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps(src))
    return f


def _item_row(send_to_splitwise, for_who):
    return [46237, 14.07, "Fakebrand ForceFlex Trash Bags", "", send_to_splitwise, "",
            "Amazon Card", for_who, "", "", AMAZON_NOTE]


@pytest.mark.parametrize("send_to_splitwise, for_who", [
    (False, "Both"),        # Personal: unticked, stays out of Splitwise
    (True, "Partner"),        # Partner's: credits her in full
])
def test_refund_copies_the_item_rows_classification(amazon_month, tmp_path,
                                                    send_to_splitwise, for_who):
    f = _amazon_file_with_refund(amazon_month)
    rd, wr = _run([str(f)], existing_rows=[_item_row(send_to_splitwise, for_who)],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    [refund] = _sheet_rows(wr)
    assert refund[0] == "08/20/2026"
    assert refund[1] == -12.99
    assert refund[4] is send_to_splitwise
    assert refund[7] == for_who
    assert refund[10] == AMAZON_REFUND_NOTE


def test_refund_for_an_item_in_the_same_run_takes_the_defaults(amazon_month, tmp_path):
    f = _amazon_file_with_refund(amazon_month)
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    item, refund = _sheet_rows(wr)
    assert item[10] == AMAZON_NOTE
    assert refund[1] == -12.99
    assert refund[4] is True
    assert refund[7] is None


def test_rescrape_does_not_duplicate_a_refund(amazon_month, tmp_path):
    f = _amazon_file_with_refund(amazon_month)
    existing = [_item_row(False, "Both"),
                [46254, -12.99, "Refund: Fakebrand ForceFlex Trash Bags", "", False, "",
                 "Amazon Card", "Both", "", "",
                 AMAZON_REFUND_NOTE]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


def test_refund_is_not_mistaken_for_its_item_row(amazon_month, tmp_path):
    # An existing Refund row's Notes contain the Item key; it must not stand in
    # for the Item row itself.
    f = _amazon_file_with_refund(amazon_month)
    existing = [[46254, -1.00, "Refund", "", False, "", "Amazon Card", "Both", "", "",
                 f"{AMAZON_NOTE} refund 2026-08-10 1.00"]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    item, refund = _sheet_rows(wr)
    assert item[10] == AMAZON_NOTE
    assert refund[4] is True and refund[7] is None


def test_refund_whose_item_row_is_missing_is_held_with_a_warning(amazon_month, tmp_path, capsys):
    # The Item's Order failed the total check, so no Item row exists anywhere.
    f = _amazon_file_with_refund(amazon_month)
    src = json.loads(f.read_text())
    src["orders"][0]["order_total"] = 99.99
    f.write_text(json.dumps(src))
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    out = capsys.readouterr().out
    assert "'refund without item row': 1" in out
    assert "111-0000000-0000001 #1" in out and "12.99" in out


def test_refund_whose_item_row_has_an_odd_e_cell_is_held_not_fatal(amazon_month, tmp_path, capsys):
    f = _amazon_file_with_refund(amazon_month)
    rd, wr = _run([str(f)], existing_rows=[_item_row("yes", "Partner")],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    assert "'refund with unreadable item row': 1" in capsys.readouterr().out


def test_odd_e_cell_on_an_unrelated_item_row_does_not_block_a_card_import(csv_file, tmp_path):
    rd, wr = _run([str(csv_file)], existing_rows=[_item_row("yes", "Partner")],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_called_once()


def test_refund_already_in_the_sheet_does_not_warn_when_its_item_row_is_gone(
        amazon_month, tmp_path, capsys):
    f = _amazon_file_with_refund(amazon_month)
    src = json.loads(f.read_text())
    src["orders"][0]["order_total"] = 99.99      # no Item row this run either
    f.write_text(json.dumps(src))
    existing = [[46254, -12.99, "Refund", "", False, "", "Amazon Card", "Both",
                 "", "", AMAZON_REFUND_NOTE]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    assert "refund without item row" not in capsys.readouterr().out


def _amazon_file_without_ship_date(amazon_month, order_date):
    src = json.loads(AMAZON_FIXTURE.read_text())
    src["orders"][0]["order_date"] = order_date
    src["orders"][0]["shipments"][0]["ship_date"] = None
    f = amazon_month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps(src))
    return f


def test_unknown_ship_date_row_notes_say_so_and_a_rescrape_writes_nothing(amazon_month, tmp_path, capsys):
    f = _amazon_file_without_ship_date(amazon_month, "2026-08-03")
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [
        AMAZON_NOTE + " (ship date unknown, Order Date used for cutoff)"]
    assert "111-0000000-0000001" in capsys.readouterr().out

    # The sheet now holds that row; a re-scrape must recognise it by its key.
    existing = [[46237, 14.07, "Trash bags", "", True, "", "Amazon Card", "", "", "",
                 "split-transactions automation amazon 111-0000000-0000001 #1"
                 " (ship date unknown, Order Date used for cutoff)"]]
    rescrape = json.loads(f.read_text())
    rescrape["scraped_on"] = "2026-09-29"
    f.write_text(json.dumps(rescrape))
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log2.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


def test_untargeted_coupon_is_written_in_the_discount_term_and_warned(amazon_month, tmp_path, capsys):
    # Fixture Item: 12.99 + 1.08 tax = 14.07; a $2 coupon with no targets lowers the total.
    src = json.loads(AMAZON_FIXTURE.read_text())
    order = src["orders"][0]
    order["promos"] = [{"name": "Coupon", "amount": 2.00, "positions": []}]
    order["order_total"] = 12.07
    f = amazon_month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps(src))
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert _sheet_rows(wr)[0][1] == "=12.99+1.08-2"
    out = capsys.readouterr().out
    assert "111-0000000-0000001" in out and "2.00" in out


def _two_item_refund_file(month):
    """Items #1 (30.00) and #2 (10.00) on one Order, one Refund of 20.00 across both."""
    src = json.loads(AMAZON_FIXTURE.read_text())
    order = src["orders"][0]
    order["order_total"] = 40.00
    shipment = order["shipments"][0]
    shipment["tax"] = 0
    first, second = dict(shipment["items"][0]), dict(shipment["items"][0])
    first.update(position=1, short_name="Thing 1", unit_price=30.00, tax=0)
    second.update(position=2, short_name="Thing 2", unit_price=10.00, tax=0)
    shipment["items"] = [first, second]
    src["refunds"] = [{"order_number": "111-0000000-0000001", "positions": [1, 2],
                       "amount": 20.00, "refund_date": "2026-08-20"}]
    f = month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps(src))
    return f


def _split_item_row(position, price, send_to_splitwise, for_who):
    return [46237, price, f"Thing {position}", "", send_to_splitwise, "",
            "Amazon Card", for_who, "", "",
            f"split-transactions automation amazon 111-0000000-0000001 #{position}"]


def test_refund_across_a_personal_and_a_shared_item_classifies_each_part(amazon_month, tmp_path):
    f = _two_item_refund_file(amazon_month)
    existing = [_split_item_row(1, 30.00, False, "Both"),    # Personal
                _split_item_row(2, 10.00, True, "Partner")]    # Partner's
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    personal, partners = _sheet_rows(wr)
    assert (personal[1], personal[4], personal[7]) == (-15.00, False, "Both")
    assert (partners[1], partners[4], partners[7]) == (-5.00, True, "Partner")
    assert personal[10] == "split-transactions automation amazon 111-0000000-0000001 #1 refund 2026-08-20 15.00"
    assert partners[10] == "split-transactions automation amazon 111-0000000-0000001 #2 refund 2026-08-20 5.00"


def test_rescrape_does_not_duplicate_a_split_refund(amazon_month, tmp_path):
    f = _two_item_refund_file(amazon_month)
    note = "split-transactions automation amazon 111-0000000-0000001"
    existing = [_split_item_row(1, 30.00, False, "Both"),
                _split_item_row(2, 10.00, True, "Partner"),
                [46254, -15.00, "Refund: Thing 1", "", False, "", "Amazon Card",
                 "Both", "", "", f"{note} #1 refund 2026-08-20 15.00"],
                [46254, -5.00, "Refund: Thing 2", "", True, "", "Amazon Card",
                 "Partner", "", "", f"{note} #2 refund 2026-08-20 5.00"]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


# --- Whole Foods Orders ----------------------------------------------------------

WF_NOTE = "split-transactions automation amazon 111-0000000-0000002"


def _whole_foods_file(month, order_date="2026-09-11", refunds=()):
    f = month / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps({
        "schema_version": 2, "scraped_on": "2026-09-28",
        "orders": [{
            "kind": "whole_foods", "order_number": "111-0000000-0000002",
            "order_date": order_date, "delivered": True,
            "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
            "order_total": 113.99,
            "charges": [{"name": "Subtotal", "amount": 106.99},
                        {"name": "Driver tip", "amount": 7.00}],
            "discounts": [],
        }],
        "refunds": list(refunds)}))
    return f


def _wf_refund(amount=4.99, refund_date="2026-09-12"):
    return {"order_number": "111-0000000-0000002", "positions": [],
            "amount": amount, "refund_date": refund_date}


def _wf_order_row(send_to_splitwise, for_who):
    return [46276, 113.99, "Whole Foods", "", send_to_splitwise, "", "Amazon Card",
            for_who, "", "", WF_NOTE]


def test_whole_foods_order_writes_one_row_with_the_formula_and_key(amazon_month, tmp_path):
    f = _whole_foods_file(amazon_month)
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    [row] = _sheet_rows(wr)
    assert row[0] == "09/11/2026"
    assert row[1] == "=106.99+7"
    assert row[2] == "Whole Foods"
    assert row[4] is True and row[7] is None
    assert row[6] == "Amazon Card"
    assert row[10] == WF_NOTE


def test_rescrape_of_a_whole_foods_order_writes_nothing(amazon_month, tmp_path):
    f = _whole_foods_file(amazon_month)
    rd, wr = _run([str(f)], existing_rows=[_wf_order_row(False, "Both")],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


def test_whole_foods_order_before_the_cutoff_is_not_written(amazon_month, tmp_path, capsys):
    f = _whole_foods_file(amazon_month, order_date="2026-07-28")
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()
    assert "'before 2026-07-29': 1" in capsys.readouterr().out


@pytest.mark.parametrize("send_to_splitwise, for_who", [
    (False, "Both"),
    (True, "Partner"),
])
def test_whole_foods_refund_copies_the_order_rows_classification(amazon_month, tmp_path,
                                                                 send_to_splitwise, for_who):
    f = _whole_foods_file(amazon_month, refunds=[_wf_refund()])
    rd, wr = _run([str(f)], existing_rows=[_wf_order_row(send_to_splitwise, for_who)],
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    [refund] = _sheet_rows(wr)
    assert refund[0] == "09/12/2026"
    assert refund[1] == -4.99
    assert refund[2] == "Refund: Whole Foods"
    assert refund[4] is send_to_splitwise
    assert refund[7] == for_who
    assert refund[10] == f"{WF_NOTE} refund 2026-09-12 4.99"


def test_whole_foods_refund_in_the_same_run_takes_the_defaults(amazon_month, tmp_path):
    f = _whole_foods_file(amazon_month, refunds=[_wf_refund()])
    rd, wr = _run([str(f)], log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    order, refund = _sheet_rows(wr)
    assert order[10] == WF_NOTE
    assert refund[1] == -4.99 and refund[4] is True and refund[7] is None


def test_rescrape_does_not_duplicate_a_whole_foods_refund(amazon_month, tmp_path):
    f = _whole_foods_file(amazon_month, refunds=[_wf_refund()])
    existing = [_wf_order_row(False, "Both"),
                [46277, -4.99, "Refund: Whole Foods", "", False, "", "Amazon Card",
                 "Both", "", "", f"{WF_NOTE} refund 2026-09-12 4.99"]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    wr.assert_not_called()


def test_a_whole_foods_refund_row_does_not_stand_in_for_its_order_row(amazon_month, tmp_path):
    f = _whole_foods_file(amazon_month)
    existing = [[46277, -4.99, "Refund: Whole Foods", "", False, "", "Amazon Card",
                 "Both", "", "", f"{WF_NOTE} refund 2026-09-12 4.99"]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [WF_NOTE]


def test_a_whole_foods_order_key_does_not_match_an_item_row_of_the_same_prefix(amazon_month, tmp_path):
    # Whole word match: a row for "... #1" is not the Order's own row.
    f = _whole_foods_file(amazon_month)
    existing = [[46237, 5.00, "Other", "", True, "", "Amazon Card", "", "", "", f"{WF_NOTE} #1"]]
    rd, wr = _run([str(f)], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [WF_NOTE]


def test_an_item_key_is_not_hidden_by_a_whole_foods_order_row_of_the_same_prefix(amazon_month, tmp_path):
    existing = [_wf_order_row(True, "")]
    existing[0][10] = "split-transactions automation amazon 111-0000000-0000001"
    rd, wr = _run([str(amazon_month / "amazon-orders-2026-09-28.json")], existing_rows=existing,
                  log_path=tmp_path / "log.json", accounts_map=AMAZON_ACCOUNTS)
    assert [row[10] for row in _sheet_rows(wr)] == [AMAZON_NOTE]
