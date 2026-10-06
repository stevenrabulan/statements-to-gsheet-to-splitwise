import json
from datetime import date, datetime
from pathlib import Path

from models import AccountConfig, ImporterError, SheetConfig

ACCOUNTS_PATH = Path(__file__).parent / "accounts.json"

# Reserved accounts.json key: the Google Sheet to write to, not an account.
SHEET_KEY = "_sheet"

# Keys permitted inside the object form of an accounts.json value.
_ALLOWED_KEYS = {"name", "ignore_before"}
_SHEET_KEYS = {"spreadsheet_id", "gid"}


def _parse_ignore_before(raw, key: str) -> date | None:
    """Parse the optional ignore_before field; null/absent means no cutoff."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{key}: ignore_before must be a YYYY-MM-DD string, got {raw!r}")
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{key}: ignore_before must be YYYY-MM-DD, got {raw!r}")


def _parse_entry(key: str, value) -> AccountConfig:
    """Accept either "Label" or {"name": "Label", "ignore_before": "YYYY-MM-DD"}."""
    if isinstance(value, dict):
        unknown = sorted(set(value) - _ALLOWED_KEYS)
        if unknown:
            raise ValueError(
                f"{key}: unknown setting(s) {unknown} — allowed: {sorted(_ALLOWED_KEYS)}"
            )
        if "name" not in value:
            raise ValueError(f'{key}: object form requires a "name" field')
        name = str(value["name"]).strip()
        ignore_before = _parse_ignore_before(value.get("ignore_before"), key)
    else:
        name = str(value).strip()
        ignore_before = None
    if not name:
        raise ValueError(f"{key}: account name must not be empty")
    return AccountConfig(name=name, ignore_before=ignore_before)


def _parse_sheet(value) -> SheetConfig:
    """Parse the "_sheet" entry: {"spreadsheet_id": "...", "gid": 0}."""
    if not isinstance(value, dict):
        raise ValueError(f"{SHEET_KEY}: must be an object with {sorted(_SHEET_KEYS)}")
    if set(value) != _SHEET_KEYS:
        raise ValueError(
            f"{SHEET_KEY}: expected exactly {sorted(_SHEET_KEYS)}, got {sorted(value)}"
        )
    spreadsheet_id, gid = value["spreadsheet_id"], value["gid"]
    if not isinstance(spreadsheet_id, str) or not spreadsheet_id.strip():
        raise ValueError(f"{SHEET_KEY}: spreadsheet_id must be a non-empty string, got {spreadsheet_id!r}")
    # bool is an int subclass; true/false is never a valid gid.
    if isinstance(gid, bool) or not isinstance(gid, int) or gid < 0:
        raise ValueError(f"{SHEET_KEY}: gid must be a whole number, got {gid!r}")
    return SheetConfig(spreadsheet_id=spreadsheet_id.strip(), gid=gid)


def _read(p: Path) -> dict:
    data = json.loads(p.read_text())
    if not isinstance(data, dict):
        raise ValueError("accounts file must be a JSON object")
    return data


def load_accounts(path: str | Path = ACCOUNTS_PATH) -> dict[str, AccountConfig]:
    """Load the filename-substring -> account-config map. Missing file = empty map."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return {
            str(k): _parse_entry(str(k), v) for k, v in _read(p).items() if k != SHEET_KEY
        }
    except (json.JSONDecodeError, ValueError) as exc:
        raise ImporterError(f"{p} is invalid: {exc}")


def load_sheet_config(path: str | Path = ACCOUNTS_PATH) -> SheetConfig:
    """Load the Google Sheet to write to. There is no default: a missing entry fails loud."""
    p = Path(path)
    hint = f'Add a "{SHEET_KEY}" entry (see accounts.example.json).'
    if not p.exists():
        raise ImporterError(f"{p} not found. {hint}")
    try:
        data = _read(p)
        if SHEET_KEY not in data:
            raise ImporterError(f"{p} does not say which Google Sheet to write to. {hint}")
        return _parse_sheet(data[SHEET_KEY])
    except (json.JSONDecodeError, ValueError) as exc:
        raise ImporterError(f"{p} is invalid: {exc}")


def account_for_filename(filename: str, mapping: dict[str, AccountConfig]) -> AccountConfig | None:
    """Return the account config whose key is a substring of filename (longest wins).

    Returns None if no key matches. Raises ImporterError if two or more keys tie
    for the longest match (ambiguous account assignment must not be silent).
    """
    matches = [k for k in mapping if k in filename]
    if not matches:
        return None
    longest = max(len(k) for k in matches)
    best = sorted(k for k in matches if len(k) == longest)
    if len(best) > 1:
        raise ImporterError(
            f"{filename}: ambiguous account — multiple accounts.json keys match equally: {best}"
        )
    return mapping[best[0]]
