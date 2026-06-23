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
        "",
        True,
        "",
        txn.account,
        "",
        "",
        "",
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


def append_transactions(transactions: list[Transaction]) -> int:
    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet_name = get_sheet_name(service, SPREADSHEET_ID, SHEET_GID)

    rows = [build_row(t) for t in transactions]
    if not rows:
        return 0

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A:K",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)
