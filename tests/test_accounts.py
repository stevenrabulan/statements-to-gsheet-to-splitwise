import json

import pytest

from accounts import load_accounts, account_for_filename
from models import ImporterError


def test_substring_match():
    m = {"Chase1111": "Chase Sapphire Reserve", "Fakecoin": "Fakecoin Card"}
    assert account_for_filename("Chase1111_Activity20260416_20260515_20260623.CSV", m) == "Chase Sapphire Reserve"
    assert account_for_filename("Fakecoin Card.csv", m) == "Fakecoin Card"


def test_longest_key_wins():
    m = {"Chase": "Generic Chase", "Chase1111": "Chase Sapphire Reserve"}
    assert account_for_filename("Chase1111_Activity.CSV", m) == "Chase Sapphire Reserve"


def test_no_match_returns_none():
    assert account_for_filename("Mystery5555.csv", {"Chase1111": "X"}) is None


def test_missing_file_returns_empty(tmp_path):
    assert load_accounts(tmp_path / "nope.json") == {}


def test_roundtrip(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"Chase1111": "Chase Sapphire Reserve"}))
    assert load_accounts(p) == {"Chase1111": "Chase Sapphire Reserve"}


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
    m = {"Visa": "Visa Generic", "Visa1234": "Visa Platinum"}
    assert account_for_filename("Visa1234_Activity.CSV", m) == "Visa Platinum"


def test_equal_length_ambiguous_raises():
    m = {"Chase1111": "Sapphire", "Chase8842": "Checking"}
    with pytest.raises(ImporterError):
        account_for_filename("Chase1111_and_Chase8842_weird.CSV", m)


def test_coerces_non_string_values(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text('{"123": 456}')
    assert load_accounts(p) == {"123": "456"}
