from pdf_parser import parse_transactions
from models import Transaction
from datetime import date

SAMPLE_TEXT = """
ACCOUNT ACTIVITY

Date        Description                     Amount
05/20       WHOLE FOODS MARKET              45.67
05/22       NETFLIX.COM                     15.99
05/23       PAYMENT THANK YOU              -500.00
06/01       AMAZON PRIME                    14.99
"""

def test_parse_returns_transactions():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    assert len(txns) == 3  # payment excluded, 3 purchases

def test_transaction_fields():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    t = txns[0]
    assert t.date == date(2026, 5, 20)
    assert t.description == "WHOLE FOODS MARKET"
    assert t.amount == 45.67
    assert t.account == "Chase Sapphire"

def test_excludes_payments():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    descriptions = [t.description for t in txns]
    assert "PAYMENT THANK YOU" not in descriptions

def test_parse_empty_text():
    txns = parse_transactions("", card_name="Chase Sapphire", year=2026)
    assert txns == []

def test_year_rollover_december_billing_start():
    """Jan transactions on a Dec→Jan statement should get year+1."""
    from datetime import date as dt
    text = """
12/20       WHOLE FOODS MARKET              45.67
01/05       NETFLIX.COM                     15.99
"""
    billing_start = dt(2025, 12, 16)
    txns = parse_transactions(text, card_name="Chase", year=2025, billing_start=billing_start)
    dec_txn = next(t for t in txns if t.description == "WHOLE FOODS MARKET")
    jan_txn = next(t for t in txns if t.description == "NETFLIX.COM")
    assert dec_txn.date.year == 2025
    assert jan_txn.date.year == 2026
