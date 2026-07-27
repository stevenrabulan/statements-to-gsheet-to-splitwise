import json
from datetime import date, datetime
from pathlib import Path

from models import AccountConfig, ImporterError

ACCOUNTS_PATH = Path(__file__).parent / "accounts.json"

# Keys permitted inside the object form of an accounts.json value.
_ALLOWED_KEYS = {"name", "ignore_before"}


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


def load_accounts(path: str | Path = ACCOUNTS_PATH) -> dict[str, AccountConfig]:
    """Load the filename-substring -> account-config map. Missing file = empty map."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            raise ValueError("accounts file must be a JSON object")
        return {str(k): _parse_entry(str(k), v) for k, v in data.items()}
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
