import json
from datetime import date

import pytest

from accounts import load_accounts, load_sheet_config, account_for_filename
from models import AccountConfig, ImporterError, SheetConfig


def _map(**kwargs) -> dict[str, AccountConfig]:
    return {k: AccountConfig(name=v) for k, v in kwargs.items()}


def test_substring_match():
    m = _map(Chase1111="Chase Sapphire Reserve", Fakecoin="Fakecoin Card")
    assert account_for_filename("Chase1111_Activity20260416_20260515_20260623.CSV", m).name == "Chase Sapphire Reserve"
    assert account_for_filename("Fakecoin Card.csv", m).name == "Fakecoin Card"


def test_longest_key_wins():
    m = _map(Chase="Generic Chase", Chase1111="Chase Sapphire Reserve")
    assert account_for_filename("Chase1111_Activity.CSV", m).name == "Chase Sapphire Reserve"


def test_no_match_returns_none():
    assert account_for_filename("Mystery5555.csv", _map(Chase1111="X")) is None


def test_missing_file_returns_empty(tmp_path):
    assert load_accounts(tmp_path / "nope.json") == {}


def test_roundtrip(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"Chase1111": "Chase Sapphire Reserve"}))
    assert load_accounts(p) == {"Chase1111": AccountConfig("Chase Sapphire Reserve")}


def test_invalid_json_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text("{ not json")
    with pytest.raises(ImporterError):
        load_accounts(p)


def test_non_object_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text("[1, 2, 3]")
    with pytest.raises(ImporterError):
        load_accounts(p)


def test_substring_key_of_longer_key_not_ambiguous():
    m = _map(Visa="Visa Generic", Visa1234="Visa Platinum")
    assert account_for_filename("Visa1234_Activity.CSV", m).name == "Visa Platinum"


def test_equal_length_ambiguous_raises():
    m = _map(Chase1111="Sapphire", Chase8842="Checking")
    with pytest.raises(ImporterError):
        account_for_filename("Chase1111_and_Chase8842_weird.CSV", m)


def test_coerces_non_string_values(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"123": 456}')
    assert load_accounts(p) == {"123": AccountConfig("456")}


def test_string_form_has_no_cutoff(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"Chase1111": "Sapphire"}')
    assert load_accounts(p)["Chase1111"].ignore_before is None


def test_object_form_parses_ignore_before(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card", "ignore_before": "2026-06-01"}}')
    cfg = load_accounts(p)["FakeMart"]
    assert cfg == AccountConfig("FakeMart Card", date(2026, 6, 1))


def test_object_form_without_ignore_before(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card"}}')
    assert load_accounts(p)["FakeMart"] == AccountConfig("FakeMart Card", None)


def test_null_ignore_before_means_no_cutoff(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card", "ignore_before": null}}')
    assert load_accounts(p)["FakeMart"].ignore_before is None


def test_object_form_requires_name(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"ignore_before": "2026-06-01"}}')
    with pytest.raises(ImporterError, match="name"):
        load_accounts(p)


def test_bad_ignore_before_format_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card", "ignore_before": "06/01/2026"}}')
    with pytest.raises(ImporterError, match="YYYY-MM-DD"):
        load_accounts(p)


def test_non_string_ignore_before_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card", "ignore_before": 20260601}}')
    with pytest.raises(ImporterError, match="YYYY-MM-DD"):
        load_accounts(p)


def test_unknown_setting_raises(tmp_path):
    """Typos like ignore-before must fail loud, not silently disable the cutoff."""
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": {"name": "FakeMart Card", "ignore-before": "2026-06-01"}}')
    with pytest.raises(ImporterError, match="ignore-before"):
        load_accounts(p)


def test_empty_name_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"FakeMart": "   "}')
    with pytest.raises(ImporterError, match="empty"):
        load_accounts(p)


def _sheet_file(tmp_path, sheet):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"Chase1111": "Chase Sapphire Reserve", "_sheet": sheet}))
    return p


def test_sheet_config_loads(tmp_path):
    p = _sheet_file(tmp_path, {"spreadsheet_id": "abc123", "gid": 42})
    assert load_sheet_config(p) == SheetConfig(spreadsheet_id="abc123", gid=42)


def test_sheet_entry_is_not_an_account(tmp_path):
    p = _sheet_file(tmp_path, {"spreadsheet_id": "abc123", "gid": 42})
    assert load_accounts(p) == {"Chase1111": AccountConfig("Chase Sapphire Reserve")}


def test_sheet_config_missing_file_raises(tmp_path):
    with pytest.raises(ImporterError, match="_sheet"):
        load_sheet_config(tmp_path / "nope.json")


def test_sheet_config_missing_entry_raises(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"Chase1111": "Chase Sapphire Reserve"}')
    with pytest.raises(ImporterError, match="_sheet"):
        load_sheet_config(p)


@pytest.mark.parametrize("sheet", [
    "abc123",
    {"spreadsheet_id": "abc123"},
    {"spreadsheet_id": "abc123", "gid": 42, "tab": "Split payments"},
    {"spreadsheet_id": "  ", "gid": 42},
    {"spreadsheet_id": 123, "gid": 42},
    {"spreadsheet_id": "abc123", "gid": "42"},
    {"spreadsheet_id": "abc123", "gid": True},
    {"spreadsheet_id": "abc123", "gid": -1},
])
def test_bad_sheet_entry_raises(tmp_path, sheet):
    with pytest.raises(ImporterError, match="_sheet"):
        load_sheet_config(_sheet_file(tmp_path, sheet))
