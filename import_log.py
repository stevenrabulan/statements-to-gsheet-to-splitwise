import hashlib
import json
from pathlib import Path

LOG_PATH = Path(__file__).parent / "import_log.json"


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_log(path: str | Path = LOG_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, list):
            raise ValueError("import log is not a list")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"WARNING: {p} is corrupt ({exc}); starting fresh.")
        return []


def find_by_hash(sha256: str, log: list[dict]) -> dict | None:
    for entry in log:
        if entry.get("sha256") == sha256:
            return entry
    return None


def append_entry(entry: dict, path: str | Path = LOG_PATH) -> None:
    log = load_log(path)
    log.append(entry)
    Path(path).write_text(json.dumps(log, indent=2))
