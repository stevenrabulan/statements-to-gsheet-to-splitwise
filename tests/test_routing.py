import pytest

from models import ImporterError
from adapters import detect_adapter, SOURCE_MAP


FAKECOIN_HEADER = ["Date", "Amount", "Currency", "Type", "Status", "Merchant",
                   "Card Last Four", "Reward Amount", "Reward Currency",
                   "Reward Status", "Reward Rate"]


def test_detects_fakecoin():
    assert detect_adapter(FAKECOIN_HEADER).NAME == "fakecoin"


def test_unrecognized_header_raises_with_listing():
    with pytest.raises(ImporterError) as exc:
        detect_adapter(["Foo", "Bar"])
    msg = str(exc.value).lower()
    assert "fakecoin" in msg          # lists supported accounts
    assert "foo" in msg               # echoes the unrecognized header



def test_source_map_has_pdf_and_fakecoin():
    assert "fakecoin" in SOURCE_MAP and "pdf" in SOURCE_MAP
