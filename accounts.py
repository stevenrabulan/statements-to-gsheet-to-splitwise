import json
from pathlib import Path

from models import ImporterError

ACCOUNTS_PATH = Path(__file__).parent / "accounts.json"


def load_accounts(path: str | Path = ACCOUNTS_PATH) -> dict[str, str]:
    """Load the filename-substring -> account-name map. Missing file = empty map."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            raise ValueError("accounts file must be a JSON object")
        return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError) as exc:
        raise ImporterError(f"{p} is invalid: {exc}")


def account_for_filename(filename: str, mapping: dict[str, str]) -> str | None:
    """Return the account name whose key is a substring of filename (longest wins).

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
