from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from models import SheetConfig, Transaction
from sheets_writer import build_row

SHEET = SheetConfig(spreadsheet_id="sheet-id-from-config", gid=7)


def _txn(**kw):
    base = dict(date=date(2026, 5, 20), description="WHOLE FOODS MARKET",
                amount=45.67, account="Chase Sapphire Reserve",
                source_file="Chase Sapphire Reserve.csv")
    base.update(kw)
    return Transaction(**base)


def test_build_row_fields():
    row = build_row(_txn())
    assert row[0] == "05/20/2026"
    assert row[1] == 45.67
    assert row[2] == "WHOLE FOODS MARKET"
    assert row[3] is None
    assert row[4] is True
    assert row[5] is None
    assert row[6] == "Chase Sapphire Reserve"
    assert row[7] is None and row[8] is None and row[9] is None
    assert row[10] == "split-transactions automation Chase Sapphire Reserve.csv"
    assert len(row) == 11


def test_build_row_date_format():
    row = build_row(_txn(date=date(2026, 1, 5)))
    assert row[0] == "01/05/2026"


def test_k_note_falls_back_when_source_file_empty():
    row = build_row(_txn(source_file=""))
    assert row[10] == "split-transactions automation"


@patch("sheets_writer.build")
@patch("sheets_writer._get_credentials")
@patch("sheets_writer.get_sheet_name", return_value="Sheet1")
@patch("sheets_writer.load_sheet_config", return_value=SHEET)
def test_read_existing_rows_returns_values(mock_sheet, mock_name, mock_creds, mock_build):
    service = MagicMock()
    (service.spreadsheets.return_value.values.return_value
        .get.return_value.execute.return_value) = {"values": [["06/01/2026", "5.00"]]}
    mock_build.return_value = service

    from sheets_writer import read_existing_rows
    rows = read_existing_rows()
    assert rows == [["06/01/2026", "5.00"]]

    # Dedup depends on raw serials/floats, not the sheet's display format.
    kwargs = (service.spreadsheets.return_value.values.return_value
              .get.call_args.kwargs)
    assert kwargs["valueRenderOption"] == "UNFORMATTED_VALUE"
    # The sheet comes from accounts.json, never from a constant in the code.
    assert kwargs["spreadsheetId"] == "sheet-id-from-config"
    mock_name.assert_called_once_with(service, "sheet-id-from-config", 7)


@patch("sheets_writer.build")
@patch("sheets_writer._get_credentials")
@patch("sheets_writer.get_sheet_name", return_value="Sheet1")
@patch("sheets_writer.load_sheet_config", return_value=SHEET)
def test_read_existing_rows_empty_sheet(mock_sheet, mock_name, mock_creds, mock_build):
    service = MagicMock()
    (service.spreadsheets.return_value.values.return_value
        .get.return_value.execute.return_value) = {}
    mock_build.return_value = service

    from sheets_writer import read_existing_rows
    assert read_existing_rows() == []


@patch("sheets_writer.TOKEN_FILE")
@patch("sheets_writer.Credentials")
@patch("sheets_writer.InstalledAppFlow")
def test_get_credentials_handles_refresh_error(mock_flow_cls, mock_creds_cls, mock_token_file):
    from google.auth.exceptions import RefreshError
    mock_token_file.exists.return_value = True

    expired_creds = MagicMock()
    expired_creds.valid = False
    expired_creds.expired = True
    expired_creds.refresh_token = "some_refresh_token"
    expired_creds.refresh.side_effect = RefreshError("invalid_grant")

    mock_creds_cls.from_authorized_user_file.return_value = expired_creds

    new_creds = MagicMock()
    new_creds.to_json.return_value = '{"token": "new"}'
    flow_instance = MagicMock()
    flow_instance.run_local_server.return_value = new_creds
    mock_flow_cls.from_client_secrets_file.return_value = flow_instance

    from sheets_writer import _get_credentials
    res = _get_credentials()
    assert res == new_creds
    flow_instance.run_local_server.assert_called_once()


def test_build_row_refuses_a_note_suffix_without_a_key():
    with pytest.raises(AssertionError):
        build_row(_txn(note_suffix=" (ship date unknown)"))
