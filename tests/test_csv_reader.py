from csv_reader import read_csv_text

COMMA = "Date,Amount,Type\n2026-06-01,12.50,PURCHASE\n"
TAB = "Date\tAmount\tType\n2026-06-01\t12.50\tPURCHASE\n"
PADDED = " Date , Amount , Type \n2026-06-01,12.50,PURCHASE\n"


def test_reads_comma():
    header, rows = read_csv_text(COMMA)
    assert header == ["Date", "Amount", "Type"]
    assert rows == [{"Date": "2026-06-01", "Amount": "12.50", "Type": "PURCHASE"}]


def test_reads_tab():
    header, rows = read_csv_text(TAB)
    assert header == ["Date", "Amount", "Type"]
    assert rows[0]["Type"] == "PURCHASE"


def test_strips_header_whitespace():
    header, rows = read_csv_text(PADDED)
    assert header == ["Date", "Amount", "Type"]
    assert rows[0]["Amount"] == "12.50"


def test_empty_text():
    header, rows = read_csv_text("")
    assert header == [] and rows == []
