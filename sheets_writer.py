from datetime import date
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from models import Transaction

SPREADSHEET_ID = "YOUR_SPREADSHEET_ID"
SHEET_GID = 0
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"


def _k_note(source_file: str) -> str:
    sf = (source_file or "").strip()
    return f"split-transactions automation {sf}" if sf else "split-transactions automation"


def build_row(txn: Transaction) -> list:
    return [
        txn.date.strftime("%m/%d/%Y"),
        txn.amount,
        txn.description,
        None,
        True,
        None,
        txn.account,
        None,
        None,
        None,
        _k_note(txn.source_file),
    ]


def _get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_sheet_name(service, spreadsheet_id: str, gid: int) -> str:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["sheetId"] == gid:
            return sheet["properties"]["title"]
    raise ValueError(f"No sheet found with gid={gid}")


def read_existing_rows() -> list[list]:
    """Read the tab's A:K for dedup. Returns raw cell values (no parsing)."""
    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet_name = get_sheet_name(service, SPREADSHEET_ID, SHEET_GID)
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{sheet_name}'!A:K")
        .execute()
    )
    return resp.get("values", [])


def append_transactions(transactions: list[Transaction], start_search_row: int = 1) -> tuple[int, int, int]:
    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet_name = get_sheet_name(service, SPREADSHEET_ID, SHEET_GID)

    rows = [build_row(t) for t in transactions]
    if not rows:
        return 0, 0, 0

    existing_rows = read_existing_rows()
    target_row_idx = max(len(existing_rows) + 1, start_search_row)
    
    start_index = max(1, start_search_row - 1)
    for i in range(start_index, len(existing_rows)):
        row = existing_rows[i]
        a_val = str(row[0]).strip() if len(row) > 0 else ""
        b_val = str(row[1]).strip() if len(row) > 1 else ""
        if not a_val and not b_val:
            target_row_idx = i + 1
            break

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A{target_row_idx}",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()

    end_row_idx = target_row_idx + len(rows) - 1
    return len(rows), target_row_idx, end_row_idx
