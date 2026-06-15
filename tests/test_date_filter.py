from datetime import date
from date_filter import billing_window, in_window

def test_billing_window_mid_month():
    start, end = billing_window(today=date(2026, 6, 10))
    assert start == date(2026, 5, 16)
    assert end == date(2026, 6, 15)

def test_billing_window_before_16th():
    start, end = billing_window(today=date(2026, 6, 1))
    assert start == date(2026, 5, 16)
    assert end == date(2026, 6, 15)

def test_billing_window_on_16th():
    start, end = billing_window(today=date(2026, 6, 16))
    assert start == date(2026, 6, 16)
    assert end == date(2026, 7, 15)

def test_billing_window_january():
    start, end = billing_window(today=date(2026, 1, 5))
    assert start == date(2025, 12, 16)
    assert end == date(2026, 1, 15)

def test_in_window_inclusive():
    start, end = date(2026, 5, 16), date(2026, 6, 15)
    assert in_window(date(2026, 5, 16), start, end) is True
    assert in_window(date(2026, 6, 15), start, end) is True
    assert in_window(date(2026, 5, 15), start, end) is False
    assert in_window(date(2026, 6, 16), start, end) is False
