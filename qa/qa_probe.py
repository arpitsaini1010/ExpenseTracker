"""
QA probe script - Comprehensive test runner for SmartExpense.
Tests all Functional & Non-Functional Requirements, Security, Data Isolation,
Edge-case Validations, and Business Rules with CSRF Protection ENABLED.
"""
import os
import re
import sys
import time
import tempfile
import uuid
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app import create_app
from config import Config
from models import db, User, Expense, Budget

temp_db_path = os.path.join(tempfile.gettempdir(), f"qa_test_{uuid.uuid4().hex}.db").replace("\\", "/")

class QAConfig(Config):
    TESTING = True
    PROPAGATE_EXCEPTIONS = False
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{temp_db_path}"
    WTF_CSRF_ENABLED = True
    SECRET_KEY = "qa-comprehensive-secret-key"

app = create_app(QAConfig)
RESULTS = []

def record(tid, title, ok, detail=""):
    RESULTS.append((tid, title, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid}: {title}" + (f"  -> {detail}" if detail else ""))

def csrf_from(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html) or \
        re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    return m.group(1) if m else None

def new_client():
    return app.test_client()

def register(c, email, name="QA User", pw="password123"):
    html = c.get("/register").get_data(as_text=True)
    tok = csrf_from(html)
    return c.post("/register", data={
        "name": name,
        "email": email,
        "password": pw,
        "confirm_password": pw,
        "csrf_token": tok
    }, follow_redirects=False)

def login(c, email, pw="password123", next_url=None):
    url = "/login" + (f"?next={next_url}" if next_url else "")
    tok = csrf_from(c.get(url).get_data(as_text=True))
    return c.post(url, data={
        "email": email,
        "password": pw,
        "csrf_token": tok
    }, follow_redirects=False)

def page_token(c, url="/dashboard"):
    return csrf_from(c.get(url).get_data(as_text=True))

def make_user(email, name="QA User"):
    c = new_client()
    register(c, email, name)
    login(c, email)
    return c

try:
    with app.app_context():
        db.drop_all()
        db.create_all()

    print("\n=== 1. SECURITY & CSRF (NFR-SEC-01 to 07, FR-AUTH) ===")
    c = new_client()
    r = c.post("/login", data={"email": "x@y.com", "password": "password123"})
    record("SEC-01", "POST /login without CSRF token is rejected with 400", r.status_code == 400, f"status={r.status_code}")
    body = r.get_data(as_text=True)
    record("SEC-02", "CSRF failure shows friendly branded error page (NFR-REL-03/USE-03)",
           "SmartExpense" in body and "Security token error" in body, f"starts: {body[:100]!r}")

    u = make_user("sec@example.com")
    r = u.post("/logout")
    record("SEC-03", "POST /logout without CSRF token is rejected with 400", r.status_code == 400, f"status={r.status_code}")
    r = u.get("/logout")
    record("SEC-04", "GET /logout redirects safely to login (no raw 405/crash)", r.status_code == 302 and "/login" in r.headers.get("Location", ""),
           f"status={r.status_code}, loc={r.headers.get('Location')}")

    # Cookie flags check
    c_cookie = new_client()
    register(c_cookie, "cookie@example.com")
    r_log = login(c_cookie, "cookie@example.com")
    cookies = r_log.headers.getlist("Set-Cookie")
    sc = " | ".join(cookies)
    record("SEC-05", "Session cookie is HttpOnly (NFR-SEC-06)", "httponly" in sc.lower(), sc[:120])
    record("SEC-06", "Session cookie has SameSite=Lax (NFR-SEC-06)", "samesite=lax" in sc.lower(), sc[:120])

    # Cache headers check
    r_dash = u.get("/dashboard")
    cc = r_dash.headers.get("Cache-Control", "")
    record("SEC-07", "Authenticated pages send Cache-Control: no-store (TC-07 / Privacy)",
           "no-store" in cc, f"Cache-Control={cc!r}")

    # Open redirect protection
    attacks = ["//evil.com", "/\\evil.com", "///evil.com", "https://evil.com", "javascript:alert(1)", "/\\/evil.com"]
    all_safe = True
    for idx, a in enumerate(attacks):
        c_redir = new_client()
        mail = f"redir_{idx}@example.com"
        register(c_redir, mail)
        r_atk = login(c_redir, mail, next_url=a)
        loc = r_atk.headers.get("Location", "")
        safe = (loc == "/dashboard" or loc == "http://localhost/dashboard")
        if not safe:
            all_safe = False
    record("SEC-08", "Open redirect attacks safely sanitized to /dashboard", all_safe)

    # Valid next parameter
    c_next = new_client()
    register(c_next, "nextok@example.com")
    r_next = login(c_next, "nextok@example.com", next_url="/budget")
    record("SEC-09", "Valid next=/budget returns user to /budget (FR-AUTH-08)", r_next.headers.get("Location", "").endswith("/budget"),
           r_next.headers.get("Location", ""))

    # XSS in user name & description
    xs = make_user("xss@example.com", name="<script>alert(1)</script>")
    html_xs = xs.get("/dashboard").get_data(as_text=True)
    record("SEC-10", "User name is HTML-escaped in navbar (NFR-SEC-04)",
           "&lt;script&gt;alert(1)&lt;/script&gt;" in html_xs and "<script>alert(1)</script>" not in html_xs)

    print("\n=== 2. DATA ISOLATION (FR-AUTH-11, BR-07, NFR-SEC-08) ===")
    a = make_user("alice@example.com", "Alice")
    b = make_user("bob@example.com", "Bob")

    with app.app_context():
        ua = User.query.filter_by(email="alice@example.com").first()
        ub = User.query.filter_by(email="bob@example.com").first()
        eb = Expense(user_id=ub.id, amount=777, category="Food", payment_mode="Cash", expense_date=date.today(), description="BOBSECRET")
        bb = Budget(user_id=ub.id, month=date.today().strftime("%Y-%m"), amount=55555)
        db.session.add_all([eb, bb])
        db.session.commit()
        eb_id = eb.id

    record("ISO-01", "Alice cannot GET Bob's expense edit page (returns 404)", a.get(f"/expenses/{eb_id}/edit").status_code == 404)
    tok_a = page_token(a, "/expenses")
    res_del = a.post(f"/expenses/{eb_id}/delete", data={"csrf_token": tok_a})
    with app.app_context():
        still_exists = db.session.get(Expense, eb_id) is not None
    record("ISO-02", "Alice cannot DELETE Bob's expense (returns 404, expense intact)", res_del.status_code == 404 and still_exists)
    
    html_a = a.get("/dashboard").get_data(as_text=True) + a.get("/expenses").get_data(as_text=True) + a.get("/budget").get_data(as_text=True)
    record("ISO-03", "Alice's dashboard, expenses, and budget never contain Bob's private data",
           "BOBSECRET" not in html_a and "55,555" not in html_a)

    anon = new_client()
    for path in ["/dashboard", "/expenses", "/expenses/add", "/budget", f"/expenses/{eb_id}/edit"]:
        r_anon = anon.get(path)
        record("AUTH-01", f"Anonymous access to {path} redirects to /login", r_anon.status_code == 302 and "/login" in r_anon.headers.get("Location", ""))
    record("AUTH-02", "Logged-in user visiting /login redirected to /dashboard (FR-AUTH-09)", a.get("/login").status_code == 302)
    record("AUTH-03", "Logged-in user visiting /register redirected to /dashboard (FR-AUTH-09)", a.get("/register").status_code == 302)

    print("\n=== 3. INPUT VALIDATION & RELIABILITY (FR-EXP, FR-BUD, NFR-REL-01) ===")
    w = make_user("worker@example.com")
    for bad_m in ["abc", "2026-13", "2026-00", "", "' OR 1=1 --", "<script>"]:
        r_bad_m = w.get(f"/dashboard?month={bad_m}")
        record("REL-01", f"GET /dashboard?month={bad_m!r} safely falls back to current month", r_bad_m.status_code == 200)

    # Budget amount and month checks
    tok_b = page_token(w, "/budget")
    r_bad_b = w.post("/budget", data={"month": "2026-15", "amount": 1000, "csrf_token": tok_b}, follow_redirects=True)
    record("REL-02", "Invalid budget month rejected with visible validation error",
           "Invalid month format" in r_bad_b.get_data(as_text=True))

    # Expense amounts (FR-EXP-02: 1 to 1,000,000 whole rupees)
    amts = {"0": False, "-5": False, "12.5": False, "abc": False, "1000001": False, "1000000": True, "1": True, "500": True}
    for amt, should_pass in amts.items():
        tok_exp = page_token(w, "/expenses/add")
        with app.app_context():
            before = Expense.query.count()
        w.post("/expenses/add", data={
            "amount": amt,
            "category": "Food",
            "expense_date": date.today().isoformat(),
            "payment_mode": "Cash",
            "csrf_token": tok_exp
        })
        with app.app_context():
            saved = Expense.query.count() > before
        record("VAL-01", f"Expense amount {amt!r} {'accepted' if should_pass else 'rejected'}", saved == should_pass)

    # Description trimming & bounds (FR-EXP-06)
    tok_exp = page_token(w, "/expenses/add")
    w.post("/expenses/add", data={
        "amount": 100,
        "category": "Food",
        "expense_date": date.today().isoformat(),
        "payment_mode": "Cash",
        "description": "   ",
        "csrf_token": tok_exp
    })
    with app.app_context():
        last_e = Expense.query.order_by(Expense.id.desc()).first()
        record("VAL-02", "Whitespace-only description stored as NULL in database", last_e.description is None)

    tok_exp = page_token(w, "/expenses/add")
    with app.app_context():
        before_c = Expense.query.count()
    w.post("/expenses/add", data={
        "amount": 100,
        "category": "Food",
        "expense_date": date.today().isoformat(),
        "payment_mode": "Cash",
        "description": "A" * 200 + "   ",
        "csrf_token": tok_exp
    })
    with app.app_context():
        saved_c = Expense.query.count() > before_c
    record("VAL-03", "200-char description with trailing spaces accepted after trimming", saved_c)

    print("\n=== 4. BUSINESS RULES & ALGORITHMS (BR-01 to BR-08) ===")
    from utils import calculate_budget_status, calculate_forecast, format_inr_number, get_effective_budget
    # Status boundary checks
    cases = [(6999, "Normal"), (7000, "Warning"), (8999, "Warning"), (9000, "Critical"), (9999, "Critical"), (10000, "Over Budget")]
    record("BR-01", "Alert status thresholds at exact integer boundaries (₹10,000 budget)",
           all(calculate_budget_status(s, 10000)["status"] == expected for s, expected in cases))
    record("BR-02", "Utilization % rounded DOWN so 6999/10000 shows 69% Normal (DD-11)",
           calculate_budget_status(6999, 10000)["percentage"] == 69)
    record("BR-03", "11200/10000 -> 112%, visual bar capped at 100%, 'Over by ₹1,200'",
           (lambda r: r["percentage"] == 112 and r["bar_width"] == 100 and "Over by ₹1,200" in r["remaining_display"])(calculate_budget_status(11200, 10000)))
    record("BR-04", "Indian currency grouping: 123456 -> 1,23,456; 1234567 -> 12,34,567",
           format_inr_number(123456) == "1,23,456" and format_inr_number(1234567) == "12,34,567")

    # Budget inheritance rule (BR-02)
    u_inh = make_user("inherit_qa@example.com")
    with app.app_context():
        uid_inh = User.query.filter_by(email="inherit_qa@example.com").first().id
        db.session.add(Budget(user_id=uid_inh, month="2026-05", amount=18000))
        db.session.commit()
        eff_jun = get_effective_budget(uid_inh, "2026-06")
        eff_jul = get_effective_budget(uid_inh, "2026-07")
    record("BR-05", "Budget inherits from latest earlier month if current has none",
           eff_jun == 18000 and eff_jul == 18000)

    # Forecast arithmetic rounding (BR-04, FR-FOR)
    with app.app_context():
        u_for = User(name="Forecast Tester", email="forecast_qa@example.com", password_hash="x")
        db.session.add(u_for)
        db.session.commit()
        db.session.add_all([
            Expense(user_id=u_for.id, amount=10000, category="Food", payment_mode="Cash", expense_date=date(2026, 7, 1)),
            Expense(user_id=u_for.id, amount=10001, category="Food", payment_mode="Cash", expense_date=date(2026, 8, 1))
        ])
        db.session.commit()
        f_res = calculate_forecast(u_for.id, today_date=date(2026, 9, 15))
    record("BR-06", "Forecast rounds half-up: (10000+10001)/2 = 10000.5 -> ₹10,001",
           f_res["amount"] == 10001, f"forecast={f_res['amount']}")

    print("\n=== 5. PERFORMANCE & SQL AGGREGATES (NFR-PRF-01, NFR-PRF-02) ===")
    pu = make_user("perf_qa@example.com")
    with app.app_context():
        p_user = User.query.filter_by(email="perf_qa@example.com").first()
        cats = Config.CATEGORIES
        modes = Config.PAYMENT_MODES
        t_now = date.today()
        # Seed 1,000 expenses
        bulk_rows = [
            Expense(
                user_id=p_user.id,
                amount=150 + (i % 500),
                category=cats[i % len(cats)],
                payment_mode=modes[i % len(modes)],
                expense_date=t_now - timedelta(days=(i % 90))
            ) for i in range(1000)
        ]
        db.session.bulk_save_objects(bulk_rows)
        db.session.commit()

    t0 = time.perf_counter()
    r_perf = pu.get("/dashboard")
    t_elap = time.perf_counter() - t0
    record("PRF-01", "Dashboard loads in < 2 seconds with large dataset (NFR-PRF-01)",
           t_elap < 2.0 and r_perf.status_code == 200, f"elapsed={t_elap:.3f}s")

    print("\n=== 6. ERROR PAGES (NFR-REL-03) ===")
    record("ERR-01", "Unknown URL returns friendly 404 page",
           pu.get("/nonexistent-page").status_code == 404 and "Page or Record Not Found" in pu.get("/nonexistent-page").get_data(as_text=True))
    record("ERR-02", "Method Not Allowed returns friendly 405 page",
           pu.post("/dashboard").status_code == 405 and "Method Not Allowed" in pu.post("/dashboard").get_data(as_text=True))

finally:
    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
        except Exception:
            pass

print("\n" + "=" * 65)
fails = [r for r in RESULTS if not r[2]]
print(f"QA TEST SUMMARY: TOTAL {len(RESULTS)} | PASSED {len(RESULTS)-len(fails)} | FAILED {len(fails)}")
if fails:
    print("FAILED TESTS:")
    for tid, title, ok, d in fails:
        print(f"  ❌ {tid}: {title} [{d}]")
else:
    print("🎉 ALL TESTS PASSED WITH 100% SUCCESS RATE!")
print("=" * 65 + "\n")
