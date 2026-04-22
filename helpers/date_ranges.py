import datetime
from datetime import datetime as dt
from isoweek import Week
import pandas as pd

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
RELATIVE_PERIOD_LIST = ['Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days',
                        'This Week', 'Last Week', 'This Month', 'Last Month',
                        'Last 3 Months', 'This Year', 'Last Year', 'Last 5 Years', 'Last 10 Years']

_QUARTER_MAP = {
    "Q1JAN-MAR": (1, 3),
    "Q2APR-JUNE": (4, 6),
    "Q3JUL-SEP": (7, 9),
    "Q4OCT-DEC": (10, 12),
}

RELATIVE_BIANNUAL = ["Jan-June", "July-Dec"]


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

def get_biannual_start_end(period, year):
    # Validate inputs
    if period is None or year is None:
        raise ValueError("Enter Year and Period")
    if period not in RELATIVE_BIANNUAL:
        raise ValueError(f"Invalid period: {period}. Must be one of {RELATIVE_BIANNUAL}")
    try:
        year = int(year)  # Ensure year is an integer
    except (ValueError, TypeError):
        raise ValueError(f"Invalid year: {year}. Must be a valid integer (e.g., 2023)")
    
    # Map quarters to start and end months
    map = {
        "Jan-June": (1, 6),
        "July-Dec": (7, 12),
    }
    start_month, end_month = map[period]
    start_date = datetime.date(year, start_month, 1)
    # Last day of end_month
    if end_month == 12:
        end_date = datetime.date(year, 12, 31)
    else:
        end_date = datetime.date(year, end_month + 1, 1) - datetime.timedelta(days=1)
    
    return start_date, end_date

def get_relative_date_range(option):
    from datetime import datetime, timedelta
    today = datetime.today().date()
    
    if option == 'Today':
        return today, today
    elif option == 'Yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif option == 'Last 7 Days':
        start_date = today - timedelta(days=7)
        return start_date, today
    elif option == 'Last 30 Days':
        start_date = today - timedelta(days=30)
        return start_date, today
    elif option == 'This Week':
        start_date = today - timedelta(days=today.weekday())
        return start_date, today
    elif option == 'Last Week':
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
        return start_date, end_date
    elif option == 'This Month':
        start_date = today.replace(day=1)
        return start_date, today
    elif option == 'Last Month':
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        start_date = last_day_last_month.replace(day=1)
        return start_date, last_day_last_month
    # option Last 3 Months
    elif option == 'Last 3 Months':
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        last_day_two_months_ago = first_day_last_month - timedelta(days=1)
        first_day_two_months_ago = last_day_two_months_ago.replace(day=1)
        start_date = first_day_two_months_ago
        end_date = last_day_last_month
        return start_date, end_date
    # option This Year
    elif option == 'This Year':
        start_date = today.replace(month=1, day=1)
        return start_date, today
    # option Last Year
    elif option == 'Last Year':
        first_day_this_year = today.replace(month=1, day=1)
        last_day_last_year = first_day_this_year - timedelta(days=1)
        start_date = last_day_last_year.replace(month=1, day=1)
        end_date = last_day_last_year
        return start_date, end_date
    elif option == 'Last 5 Years':
        first_day_this_year = today.replace(month=1, day=1)
        last_day_last_year = first_day_this_year - timedelta(days=1)
        now = dt.now()
        start_date = now.replace(year=now.year - 5).replace(month=1, day=1)
        end_date = last_day_last_year
        return start_date, end_date
    
    elif option == 'Last 10 Years':
        first_day_this_year = today.replace(month=1, day=1)
        last_day_last_year = first_day_this_year - timedelta(days=1)
        now = dt.now()
        start_date = now.replace(year=now.year - 10).replace(month=1, day=1)
        end_date = last_day_last_year
        return start_date, end_date

    else:
        return None, None

def get_dhis2_period(start_date, period_type):
    dt = pd.to_datetime(start_date)

    if period_type == "Monthly":
        return dt.strftime("%Y%m")

    elif period_type == "Weekly":
        year, week, _ = dt.isocalendar()
        return f"{year}W{int(week):02d}"

    elif period_type == "Quarterly":
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{quarter}"

    elif period_type == "Bi-Annual":
        semester = 1 if dt.month <= 6 else 2
        return f"{dt.year}S{semester}"

    else:
        raise ValueError(f"Unsupported period type: {period_type}")
