import csv
import io
from pathlib import Path


def read_csv_text(text: str) -> tuple[list[str], list[dict]]:
    """Parse CSV text, sniffing comma vs tab from the header line.

    Returns (header, rows) where header columns and dict keys are stripped.
    """
    if not text or not text.strip():
        return [], []
    first_line = text.splitlines()[0]
    # ponytail: tab-vs-comma by presence in the header line; the four real
    # formats never mix the two. Upgrade to csv.Sniffer if a quoted-comma case appears.
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip() for h in (reader.fieldnames or [])]
    rows = [{(k.strip() if k else k): v for k, v in row.items()} for row in reader]
    return header, rows


def read_csv(path: str | Path) -> tuple[list[str], list[dict]]:
    return read_csv_text(Path(path).read_text())


if __name__ == "__main__":  # ponytail self-check
    h, r = read_csv_text("a\tb\n1\t2\n")
    assert h == ["a", "b"] and r == [{"a": "1", "b": "2"}], (h, r)
    print("ok")
