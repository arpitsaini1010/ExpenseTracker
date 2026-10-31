import re
import math
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from config import Config
from models import db, Expense, Budget

def format_inr_number(val):
    """Formats an integer into Indian comma grouping (e.g., 12,34,567)."""
    if val is None:
        return '0'
    s = str(abs(val))
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        formatted = ','.join(reversed(groups)) + ',' + last3
    return f'-{formatted}' if val < 0 else formatted

def format_currency(amount):
    """Formats amount as ₹1,23,456 or '-' if None."""
    if amount is None:
        return '-'
    return f'₹{format_inr_number(amount)}'

def format_date_display(d):
    """Formats a date object as '25 Oct 2026'."""
    if not d:
        return ''
    return d.strftime('%d %b %Y')

def get_current_month_key():
    return date.today().strftime('%Y-%m')

def validate_month_key(month_str):
    """Checks if string is valid YYYY-MM (01-12)."""
    if not month_str or not isinstance(month_str, str):
        return False
    return bool(re.match(r'^\d{4}-(0[1-9]|1[0-2])$', month_str))

def get_safe_month_key(month_param):
    """Returns valid month key or defaults to current month (BR-06)."""
    if validate_month_key(month_param):
        return month_param
    return get_current_month_key()

def get_month_date_range(month_key):
    """Returns (start_date, next_month_start_date) for month_key (BR-01)."""
    year, month = map(int, month_key.split('-'))
    start_date = date(year, month, 1)
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    return start_date, next_month_start

def get_next_month_key(month_key):
    year, month = map(int, month_key.split('-'))
    if month == 12:
        return f"{year + 1}-01"
    return f"{year:04d}-{month + 1:02d}"

def get_previous_month_key(month_key):
    year, month = map(int, month_key.split('-'))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year:04d}-{month - 1:02d}"

def get_effective_budget(user_id, month_key):
    """
    BR-02: Effective budget rule.
    row = budget of user where month == month
    if row is missing:
        row = latest budget of user where month < month
    return row.amount if row exists else None
    """
    budget_row = Budget.query.filter_by(user_id=user_id, month=month_key).first()
    if budget_row:
        return budget_row.amount
    
    # Fallback to most recent earlier month
    earlier_budget = Budget.query.filter(
        Budget.user_id == user_id,
        Budget.month < month_key
    ).order_by(Budget.month.desc()).first()
    
    if earlier_budget:
        return earlier_budget.amount
    return None

def calculate_budget_status(spent, budget):
    """
    BR-03 & Section 3.5: Budget Status and Alerts.
    Uses pure integer arithmetic for thresholds.
    Percentage displayed is rounded down (DD-11).
    """
    if budget is None:
        return {
            'status': 'No budget set',
            'percentage': None,
            'bar_width': 0,
            'color': 'secondary',
            'banner_message': None,
            'remaining': None,
            'remaining_display': '-'
        }
    
    # Integer threshold comparisons
    if spent * 100 >= budget * Config.OVER_PCT:
        status = 'Over Budget'
        color = 'dark'
    elif spent * 100 >= budget * Config.CRITICAL_PCT:
        status = 'Critical'
        color = 'danger'
    elif spent * 100 >= budget * Config.WARNING_PCT:
        status = 'Warning'
        color = 'warning'
    else:
        status = 'Normal'
        color = 'success'
    
    # Rounded down whole percentage
    percentage = (spent * 100) // budget
    bar_width = min(100, percentage)
    remaining = budget - spent

    if remaining >= 0:
        remaining_display = f"₹{format_inr_number(remaining)}"
    else:
        remaining_display = f"Over by ₹{format_inr_number(-remaining)}"

    # Banner message
    if status == 'Normal':
        banner_message = "You are on track."
    elif status == 'Warning':
        banner_message = f"Warning: you have used {percentage}% of your budget. ₹{format_inr_number(remaining)} remaining."
    elif status == 'Critical':
        banner_message = f"Critical: you have used {percentage}% of your budget. Only ₹{format_inr_number(remaining)} remaining."
    else:  # Over Budget
        banner_message = f"Over budget: you have exceeded your budget by ₹{format_inr_number(-remaining)}."

    return {
        'status': status,
        'percentage': percentage,
        'bar_width': bar_width,
        'color': color,
        'banner_message': banner_message,
        'remaining': remaining,
        'remaining_display': remaining_display
    }

def calculate_forecast(user_id, today_date=None):
    """
    BR-04 & FR-FOR: Next-month forecast based on completed months.
    Completed months = strictly before current calendar month.
    Only months with at least one expense are included.
    Returns dictionary with forecast amount, months count, message, comparison.
    """
    if today_date is None:
        today_date = date.today()
    
    current_month_key = today_date.strftime('%Y-%m')

    # Query sum of expenses grouped by month for all months strictly earlier than current month
    # In SQLite, strftime('%Y-%m', expense_date) gives the month key
    month_totals_query = db.session.query(
        func.strftime('%Y-%m', Expense.expense_date).label('month_key'),
        func.sum(Expense.amount).label('total_amount')
    ).filter(
        Expense.user_id == user_id,
        Expense.expense_date < date(today_date.year, today_date.month, 1)
    ).group_by('month_key').all()

    # Filter only months where total_amount > 0 and count of expenses >= 1
    totals = [int(row.total_amount) for row in month_totals_query if row.total_amount is not None]

    if not totals:
        return {
            'has_data': False,
            'amount': None,
            'amount_display': '-',
            'months_count': 0,
            'message': 'Not enough data yet. The forecast appears after your first completed month with expenses.',
            'budget_comparison': None
        }

    # Arithmetic mean, rounded half up to nearest whole rupee
    mean_val = Decimal(sum(totals)) / Decimal(len(totals))
    forecast_amount = int(mean_val.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    months_count = len(totals)

    # Next month key for comparison against budget
    next_month_key = get_next_month_key(current_month_key)
    effective_budget_next = get_effective_budget(user_id, next_month_key)

    budget_comparison = None
    if effective_budget_next is not None:
        if forecast_amount <= effective_budget_next:
            budget_comparison = f"Forecast is within your monthly budget of ₹{format_inr_number(effective_budget_next)}."
        else:
            diff = forecast_amount - effective_budget_next
            budget_comparison = f"Forecast exceeds your monthly budget of ₹{format_inr_number(effective_budget_next)} by ₹{format_inr_number(diff)}."

    return {
        'has_data': True,
        'amount': forecast_amount,
        'amount_display': f"₹{format_inr_number(forecast_amount)}",
        'months_count': months_count,
        'message': f"Based on {months_count} previous month{'s' if months_count > 1 else ''}",
        'budget_comparison': budget_comparison
    }

def get_chart_window_months(selected_month_key, count=6):
    """
    BR-05: Returns list of 6 month keys ending with selected_month_key, oldest to newest.
    And friendly labels like 'May 2026'.
    """
    cur = selected_month_key
    month_keys = []
    for _ in range(count):
        month_keys.append(cur)
        cur = get_previous_month_key(cur)
    month_keys.reverse()

    labels = []
    for mk in month_keys:
        y, m = map(int, mk.split('-'))
        dt = date(y, m, 1)
        labels.append(dt.strftime('%b %Y'))

    return month_keys, labels

def get_payment_mode_analysis(payment_totals_dict, total_spend):
    """
    FR-PAY: All 4 configured modes appear, sorted by amount desc.
    Modes with no spend show ₹0 and 0.0%.
    """
    modes_data = []
    for mode in Config.PAYMENT_MODES:
        amount = int(payment_totals_dict.get(mode, 0))
        if total_spend > 0:
            share = round((amount * 100.0) / total_spend, 1)
        else:
            share = 0.0
        modes_data.append({
            'mode': mode,
            'amount': amount,
            'amount_display': f"₹{format_inr_number(amount)}",
            'share': share
        })
    # Sort largest amount first (FR-PAY-04)
    modes_data.sort(key=lambda x: x['amount'], reverse=True)
    return modes_data
