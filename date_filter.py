from datetime import date
from dateutil.relativedelta import relativedelta


def billing_window(today: date | None = None) -> tuple[date, date]:
    if today is None:
        today = date.today()

    if today.day >= 16:
        start = today.replace(day=16)
        end = (today + relativedelta(months=1)).replace(day=15)
    else:
        start = (today - relativedelta(months=1)).replace(day=16)
        end = today.replace(day=15)

    return start, end


def in_window(txn_date: date, start: date, end: date) -> bool:
    return start <= txn_date <= end
