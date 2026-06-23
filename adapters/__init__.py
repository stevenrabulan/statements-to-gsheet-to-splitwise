from models import ImporterError
from . import fakecoin, discover, chase_credit, chase_checking, chase_pdf

# CSV adapters participate in header-sniff routing (in priority order).
CSV_ADAPTERS = [fakecoin, discover, chase_credit, chase_checking]

# All adapters keyed by NAME for the --source override (includes pdf).
SOURCE_MAP = {a.NAME: a for a in CSV_ADAPTERS}
SOURCE_MAP[chase_pdf.NAME] = chase_pdf


def detect_adapter(header: list[str]):
    """Return the CSV adapter whose matches() accepts this header, else raise."""
    for adapter in CSV_ADAPTERS:
        if adapter.matches(header):
            return adapter
    supported = ", ".join(a.NAME for a in CSV_ADAPTERS)
    raise ImporterError(
        f"No adapter matched CSV header {header!r}. "
        f"Supported accounts: {supported}."
    )


