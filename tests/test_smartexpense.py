import pytest
from datetime import date, timedelta
from app import create_app
from models import db, User, Expense, Budget
from config import Config
from utils import (
    calculate_budget_status,
    calculate_forecast,
    get_effective_budget,
    format_inr_number,
    format_currency,
    get_safe_month_key,
    get_month_date_range
)

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False  # Disable CSRF in tests for simpler automated requests
    SECRET_KEY = 'test-secret'

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def register_user(client, name="Test User", email="test@example.com", password="password123"):
    return client.post('/register', data={
        'name': name,
        'email': email,
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

def login_user(client, email="test@example.com", password="password123"):
    return client.post('/login', data={
        'email': email,
        'password': password
    }, follow_redirects=True)

# --- Acceptance Tests (Appendix C) ---

def test_tc01_password_length_validation(client):
    """TC-01: Register with a 7-character password (rejected)"""
    res = client.post('/register', data={
        'name': 'Short Pass',
        'email': 'short@example.com',
        'password': 'pass123',
        'confirm_password': 'pass123'
    })
    assert b"Password must be at least 8 characters" in res.data
    assert User.query.filter_by(email='short@example.com').first() is None

def test_tc02_duplicate_email_case_insensitive(client):
    """TC-02: Register an email already used, typed in different letter case"""
    register_user(client, name="User One", email="muskan@example.com")
    res = client.post('/register', data={
        'name': 'User Two',
        'email': 'MUSKAN@EXAMPLE.COM',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    assert b"This email is already registered" in res.data

def test_tc03_password_is_hashed(app, client):
    """TC-03: Register, then verify password_hash holds a salted hash, not plaintext"""
    register_user(client, email="secure@example.com", password="SecretPassword123")
    user = User.query.filter_by(email="secure@example.com").first()
    assert user is not None
    assert user.password_hash != "SecretPassword123"
    assert user.check_password("SecretPassword123") is True
    assert user.check_password("WrongPassword") is False

def test_tc04_failed_login(client):
    """TC-04: Log in with wrong password -> 'Invalid email or password'"""
    register_user(client, email="user@example.com", password="password123")
    res = client.post('/login', data={
        'email': 'user@example.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert b"Invalid email or password" in res.data

def test_tc05_login_required_redirect(client):
    """TC-05: Anonymous user opening /dashboard is redirected to /login"""
    res = client.get('/dashboard', follow_redirects=False)
    assert res.status_code == 302
    assert '/login' in res.location

def test_tc06_data_isolation_ownership(app, client):
    """TC-06: User A attempts to edit User B's expense -> 404"""
    # Create User A
    register_user(client, email="usera@example.com")
    user_a = User.query.filter_by(email="usera@example.com").first()
    
    # Create User B and expense
    user_b = User(name="User B", email="userb@example.com")
    user_b.set_password("password123")
    db.session.add(user_b)
    db.session.commit()
    
    exp_b = Expense(
        user_id=user_b.id,
        amount=500,
        category="Food",
        payment_mode="Cash",
        expense_date=date.today()
    )
    db.session.add(exp_b)
    db.session.commit()

    # Log in as User A and try to access User B's expense
    login_user(client, email="usera@example.com")
    res = client.get(f'/expenses/{exp_b.id}/edit')
    assert res.status_code == 404

def test_tc08_amount_validations(client):
    """TC-08: Add expense with invalid amounts (0, negative, > 1,000,000) rejected"""
    register_user(client, email="expuser@example.com")
    login_user(client, email="expuser@example.com")

    for bad_amt in [0, -5, 1000001]:
        res = client.post('/expenses/add', data={
            'amount': bad_amt,
            'category': 'Food',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_mode': 'Cash'
        })
        assert Expense.query.count() == 0

def test_tc09_future_date_rejected(client):
    """TC-09: Add expense dated tomorrow rejected"""
    register_user(client, email="future@example.com")
    login_user(client, email="future@example.com")
    tomorrow = date.today() + timedelta(days=1)
    res = client.post('/expenses/add', data={
        'amount': 250,
        'category': 'Food',
        'expense_date': tomorrow.strftime('%Y-%m-%d'),
        'payment_mode': 'Cash'
    })
    assert b"Expense date cannot be in the future" in res.data
    assert Expense.query.count() == 0

def test_tc10_invalid_category_rejected(client):
    """TC-10: Submitting non-whitelisted category 'Gold' rejected"""
    register_user(client, email="cat@example.com")
    login_user(client, email="cat@example.com")
    res = client.post('/expenses/add', data={
        'amount': 300,
        'category': 'Gold',
        'expense_date': date.today().strftime('%Y-%m-%d'),
        'payment_mode': 'Cash'
    })
    assert Expense.query.count() == 0

def test_tc11_valid_expense_added(client):
    """TC-11: Add valid expense -> success message and listed in its month"""
    register_user(client, email="valid@example.com")
    login_user(client, email="valid@example.com")
    res = client.post('/expenses/add', data={
        'amount': 450,
        'category': 'Travel',
        'expense_date': date.today().strftime('%Y-%m-%d'),
        'payment_mode': 'UPI',
        'description': 'Cab to college'
    }, follow_redirects=True)
    assert b"Expense of" in res.data
    assert b"Cab to college" in res.data
    assert Expense.query.count() == 1

def test_tc12_description_xss_escaped(client):
    """TC-12: Description with script tag is escaped as plain text"""
    register_user(client, email="xss@example.com")
    login_user(client, email="xss@example.com")
    script_str = "<script>alert(1)</script>"
    client.post('/expenses/add', data={
        'amount': 100,
        'category': 'Bills',
        'expense_date': date.today().strftime('%Y-%m-%d'),
        'payment_mode': 'Cash',
        'description': script_str
    }, follow_redirects=True)
    res = client.get('/expenses')
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in res.data
    assert b"<script>alert(1)</script>" not in res.data

def test_tc16_budget_upsert_same_month(client, app):
    """TC-16: Save budget for same month twice -> single record with latest amount"""
    register_user(client, email="budget@example.com")
    login_user(client, email="budget@example.com")
    m = date.today().strftime('%Y-%m')

    client.post(f'/budget?month={m}', data={'month': m, 'amount': 10000}, follow_redirects=True)
    assert Budget.query.filter_by(month=m).count() == 1
    assert Budget.query.filter_by(month=m).first().amount == 10000

    client.post(f'/budget?month={m}', data={'month': m, 'amount': 15000}, follow_redirects=True)
    assert Budget.query.filter_by(month=m).count() == 1
    assert Budget.query.filter_by(month=m).first().amount == 15000

def test_tc17_budget_inheritance(app):
    """TC-17: Budget inheritance across months (Aug 10k, Sep none -> inherits Aug)"""
    with app.app_context():
        user = User(name="Inherit", email="inherit@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        # Set Aug budget
        b_aug = Budget(user_id=user.id, month="2026-08", amount=10000)
        db.session.add(b_aug)
        db.session.commit()

        # September has no explicit budget -> inherits Aug (10,000)
        assert get_effective_budget(user.id, "2026-09") == 10000

        # Set Oct budget to 20,000 -> Sep still inherits Aug (10,000)
        b_oct = Budget(user_id=user.id, month="2026-10", amount=20000)
        db.session.add(b_oct)
        db.session.commit()

        assert get_effective_budget(user.id, "2026-09") == 10000
        assert get_effective_budget(user.id, "2026-10") == 20000
        assert get_effective_budget(user.id, "2026-11") == 20000

def test_tc19_budget_status_threshold_boundaries():
    """TC-19: Budget ₹10,000 boundary checks (6999, 7000, 8999, 9000, 9999, 10000)"""
    b = 10000
    assert calculate_budget_status(6999, b)['status'] == 'Normal'
    assert calculate_budget_status(7000, b)['status'] == 'Warning'
    assert calculate_budget_status(8999, b)['status'] == 'Warning'
    assert calculate_budget_status(9000, b)['status'] == 'Critical'
    assert calculate_budget_status(9999, b)['status'] == 'Critical'
    assert calculate_budget_status(10000, b)['status'] == 'Over Budget'
    assert calculate_budget_status(15000, b)['status'] == 'Over Budget'

def test_tc20_over_budget_display():
    """TC-20: Spend ₹11,200 against ₹10,000 budget -> bar width capped at 100%, 112%, Over by ₹1,200"""
    res = calculate_budget_status(11200, 10000)
    assert res['status'] == 'Over Budget'
    assert res['percentage'] == 112
    assert res['bar_width'] == 100
    assert "Over by ₹1,200" in res['remaining_display']

def test_tc22_fallback_invalid_month_param():
    """TC-22: Invalid month query parameter falls back to current month"""
    current_m = date.today().strftime('%Y-%m')
    assert get_safe_month_key('abc') == current_m
    assert get_safe_month_key('2026-13') == current_m
    assert get_safe_month_key('2026-05') == '2026-05'

def test_tc27_tc28_forecast_calculation(app):
    """TC-27 & 28: Forecast averages completed months, ignores current & empty months"""
    with app.app_context():
        user = User(name="Forecast", email="fore@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        today = date(2026, 10, 25)

        # Jul 12000, Aug 15000, Sep 9000, Oct (current) 5000
        e1 = Expense(user_id=user.id, amount=12000, category="Food", payment_mode="Cash", expense_date=date(2026, 7, 10))
        e2 = Expense(user_id=user.id, amount=15000, category="Food", payment_mode="Cash", expense_date=date(2026, 8, 15))
        e3 = Expense(user_id=user.id, amount=9000, category="Food", payment_mode="Cash", expense_date=date(2026, 9, 20))
        e_curr = Expense(user_id=user.id, amount=5000, category="Food", payment_mode="Cash", expense_date=date(2026, 10, 5))
        db.session.add_all([e1, e2, e3, e_curr])
        db.session.commit()

        # Forecast: (12000 + 15000 + 9000) / 3 = 12000. October ignored!
        res = calculate_forecast(user.id, today_date=today)
        assert res['has_data'] is True
        assert res['amount'] == 12000
        assert res['months_count'] == 3

        # Test TC-28: Remove Sep expense. Months with expenses: Jul (12000), Aug (15000)
        # (12000 + 15000) / 2 = 13500. Sep is empty and skipped!
        db.session.delete(e3)
        db.session.commit()

        res2 = calculate_forecast(user.id, today_date=today)
        assert res2['amount'] == 13500
        assert res2['months_count'] == 2

def test_tc07_logout_flow(client):
    """TC-07: Log out ends session and redirects to login"""
    register_user(client, email="logout@example.com")
    login_user(client, email="logout@example.com")
    res = client.post('/logout', follow_redirects=True)
    assert b"You have been logged out" in res.data
    # Dashboard should now redirect to login
    res_dash = client.get('/dashboard')
    assert res_dash.status_code == 302
    assert '/login' in res_dash.location

def test_tc13_edit_expense(client, app):
    """TC-13: Edit an expense amount, list and dashboard show updated amount"""
    register_user(client, email="editor@example.com")
    login_user(client, email="editor@example.com")
    today_str = date.today().strftime('%Y-%m-%d')
    client.post('/expenses/add', data={
        'amount': 500,
        'category': 'Food',
        'expense_date': today_str,
        'payment_mode': 'Cash'
    }, follow_redirects=True)
    
    with app.app_context():
        user = User.query.filter_by(email="editor@example.com").first()
        exp = Expense.query.filter_by(user_id=user.id).first()
        exp_id = exp.id

    client.post(f'/expenses/{exp_id}/edit', data={
        'amount': 850,
        'category': 'Food',
        'expense_date': today_str,
        'payment_mode': 'UPI',
        'description': 'Updated lunch'
    }, follow_redirects=True)

    with app.app_context():
        updated = db.session.get(Expense, exp_id)
        assert updated.amount == 850
        assert updated.payment_mode == 'UPI'

def test_tc14_delete_expense(client, app):
    """TC-14: Delete expense removes record and redirects"""
    register_user(client, email="deleter@example.com")
    login_user(client, email="deleter@example.com")
    today_str = date.today().strftime('%Y-%m-%d')
    client.post('/expenses/add', data={
        'amount': 600,
        'category': 'Travel',
        'expense_date': today_str,
        'payment_mode': 'Cash'
    }, follow_redirects=True)
    
    with app.app_context():
        user = User.query.filter_by(email="deleter@example.com").first()
        exp = Expense.query.filter_by(user_id=user.id).first()
        exp_id = exp.id

    res = client.post(f'/expenses/{exp_id}/delete', follow_redirects=True)
    assert b"Expense deleted successfully" in res.data
    with app.app_context():
        assert db.session.get(Expense, exp_id) is None

def test_tc15_month_filtering_expenses(client, app):
    """TC-15: Expenses in two different months, viewing one shows only that month with correct total"""
    register_user(client, email="filter@example.com")
    login_user(client, email="filter@example.com")

    with app.app_context():
        user = User.query.filter_by(email="filter@example.com").first()
        # Add expense in 2026-05
        e1 = Expense(user_id=user.id, amount=1200, category="Bills", payment_mode="Cash", expense_date=date(2026, 5, 10), description="May Bill")
        # Add expense in 2026-06
        e2 = Expense(user_id=user.id, amount=2400, category="Food", payment_mode="UPI", expense_date=date(2026, 6, 15), description="June Food")
        db.session.add_all([e1, e2])
        db.session.commit()

    res_may = client.get('/expenses?month=2026-05')
    assert b"May Bill" in res_may.data
    assert b"June Food" not in res_may.data
    assert b"1,200" in res_may.data

    res_june = client.get('/expenses?month=2026-06')
    assert b"June Food" in res_june.data
    assert b"May Bill" not in res_june.data
    assert b"2,400" in res_june.data

def test_tc18_new_user_no_budget_dashboard(client):
    """TC-18: New user with no budget opens dashboard -> '-' values, no error, prompt shown"""
    register_user(client, email="nobudget@example.com")
    login_user(client, email="nobudget@example.com")
    res = client.get('/dashboard')
    assert res.status_code == 200
    assert b"Set a monthly budget" in res.data or b"Set a Monthly Budget" in res.data

def test_tc21_flash_alert_on_status_warning(client):
    """TC-21: Adding an expense that moves the month into Warning shows flash alert"""
    register_user(client, email="alertwarn@example.com")
    login_user(client, email="alertwarn@example.com")
    curr_m = date.today().strftime('%Y-%m')

    # Set budget 10,000
    client.post(f'/budget?month={curr_m}', data={'month': curr_m, 'amount': 10000}, follow_redirects=True)

    # Add expense of 7,500 (75% -> Warning)
    res = client.post('/expenses/add', data={
        'amount': 7500,
        'category': 'Food',
        'expense_date': date.today().strftime('%Y-%m-%d'),
        'payment_mode': 'UPI'
    }, follow_redirects=True)

    assert b"Warning: you have used 75% of your budget" in res.data

def test_tc23_card_chart_db_sum_equality(client, app):
    """TC-23: Compare card total, chart total, and database sum for one month -> all equal"""
    register_user(client, email="mathcheck@example.com")
    login_user(client, email="mathcheck@example.com")
    curr_m = date.today().strftime('%Y-%m')

    # Add 3 expenses
    today_str = date.today().strftime('%Y-%m-%d')
    client.post('/expenses/add', data={'amount': 1500, 'category': 'Food', 'expense_date': today_str, 'payment_mode': 'Cash'}, follow_redirects=True)
    client.post('/expenses/add', data={'amount': 2500, 'category': 'Bills', 'expense_date': today_str, 'payment_mode': 'UPI'}, follow_redirects=True)
    client.post('/expenses/add', data={'amount': 1000, 'category': 'Travel', 'expense_date': today_str, 'payment_mode': 'Cash'}, follow_redirects=True)

    with app.app_context():
        user = User.query.filter_by(email="mathcheck@example.com").first()
        db_sum = db.session.query(db.func.sum(Expense.amount)).filter(Expense.user_id == user.id).scalar()
        assert db_sum == 5000

    res = client.get(f'/dashboard?month={curr_m}')
    assert b"5,000" in res.data

def test_tc25_no_expenses_month_message(client):
    """TC-25: Select a month with no expenses -> 'No expenses this month' shown"""
    register_user(client, email="emptyview@example.com")
    login_user(client, email="emptyview@example.com")
    res = client.get('/dashboard?month=2025-01')
    assert b"No expenses this month" in res.data

def test_tc26_forecast_current_month_only(app):
    """TC-26: Only current-month expenses exist -> 'Not enough data yet'"""
    with app.app_context():
        user = User(name="CurrentOnly", email="curr@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        exp = Expense(user_id=user.id, amount=3000, category="Food", payment_mode="Cash", expense_date=date.today())
        db.session.add(exp)
        db.session.commit()

        res = calculate_forecast(user.id, today_date=date.today())
        assert res['has_data'] is False
        assert "Not enough data yet" in res['message']

def test_tc29_payment_mode_breakdown(client, app):
    """TC-29: Month with only UPI expenses has all 4 modes listed, 3 at ₹0 and 0.0%"""
    register_user(client, email="upionly@example.com")
    login_user(client, email="upionly@example.com")
    today_str = date.today().strftime('%Y-%m-%d')
    client.post('/expenses/add', data={'amount': 2000, 'category': 'Food', 'expense_date': today_str, 'payment_mode': 'UPI'}, follow_redirects=True)

    res = client.get('/dashboard')
    # Check that Cash, Debit/Credit Card, Net Banking show with 0
    assert b"UPI" in res.data
    assert b"Cash" in res.data
    assert b"Debit/Credit Card" in res.data
    assert b"Net Banking" in res.data
    assert b"0.0%" in res.data

def test_tc32_welcome_message_new_user(client):
    """TC-32: New user with no expenses lands on dashboard and sees welcome message"""
    register_user(client, email="newuser@example.com")
    login_user(client, email="newuser@example.com")
    res = client.get('/dashboard')
    assert b"Welcome to SmartExpense!" in res.data

