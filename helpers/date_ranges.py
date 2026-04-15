import datetime
from isoweek import Week

RELATIVE_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

RELATIVE_QUARTERS = ["Q1 Jan-Mar", "Q2 Apr-June", "Q3 Jul-Sep", "Q4 Oct-Dec"]

_QUARTER_MAP = {
    "Q1JAN-MAR": (1, 3),
    "Q2APR-JUNE": (4, 6),
    "Q3JUL-SEP": (7, 9),
    "Q4OCT-DEC": (10, 12),
}


def get_week_start_end(week_num, year):
    """Return (start_date, end_date) for a week number and year."""
    if week_num is None or year is None:
        raise ValueError("Week and year must be specified")

    week_num = int(week_num)
    year = int(year)
    if week_num < 1 or week_num > 53:
        raise ValueError(f"Week must be between 1-53 (got {week_num})")

    week = Week(year, week_num)
    start_date = week.monday()
    end_date = start_date + datetime.timedelta(days=6)
    return start_date, end_date


def get_month_start_end(month, year):
    """Return (start_date, end_date) for a month name and year."""
    if month is None or year is None:
        raise ValueError("Month and year must be specified")
    if month not in RELATIVE_MONTHS:
        raise ValueError(f"Invalid month: {month}. Must be one of {RELATIVE_MONTHS}")

    year = int(year)
    month_index = RELATIVE_MONTHS.index(month) + 1
    start_date = datetime.date(year, month_index, 1)
    if month_index == 12:
        end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end_date = datetime.date(year, month_index + 1, 1) - datetime.timedelta(days=1)
    return start_date, end_date


def get_quarter_start_end(quarter, year):
    """Return (start_date, end_date) for a quarter label and year."""
    if quarter is None or year is None:
        raise ValueError("Quarter and year must be specified")

    year = int(year)
    normalized = quarter.replace(" ", "").upper()
    if normalized not in _QUARTER_MAP:
        raise ValueError(f"Invalid quarter: {quarter}. Must be one of {RELATIVE_QUARTERS}")

    start_month, end_month = _QUARTER_MAP[normalized]
    start_date = datetime.date(year, start_month, 1)
    if end_month == 12:
        end_date = datetime.date(year, 12, 31)
    else:
        end_date = datetime.date(year, end_month + 1, 1) - datetime.timedelta(days=1)
    return start_date, end_date
