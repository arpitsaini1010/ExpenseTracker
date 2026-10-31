"""
seed.py - Seeds demonstration user and rich sample data according to Section 8.1 of the SRS.
Can be safely run multiple times. Clears old demo data before inserting fresh data.
"""

from datetime import date, timedelta
from app import create_app
from models import db, User, Expense, Budget
from config import Config
from utils import get_previous_month_key, get_month_date_range

def seed_demo_data():
    app = create_app()
    with app.app_context():
        demo_email = "demo@smartexpense.com"
        demo_password = "Password123"
        demo_name = "Muskan Rajpal"

        print(f"--- Seeding SmartExpense Demo Data ---")
        
        # 1. Clear existing demo user if present
        existing_user = User.query.filter_by(email=demo_email).first()
        if existing_user:
            print(f"Removing previous demo data for {demo_email}...")
            db.session.delete(existing_user)
            db.session.commit()

        # 2. Create fresh demo user
        user = User(
            name=demo_name,
            email=demo_email
        )
        user.set_password(demo_password)
        db.session.add(user)
        db.session.commit()
        print(f"Created demo user: {user.name} ({user.email})")

        today = date.today()
        current_mk = today.strftime('%Y-%m')

        # 3. Determine 4 completed months
        completed_months = []
        mk = get_previous_month_key(current_mk)
        for _ in range(4):
            completed_months.append(mk)
            mk = get_previous_month_key(mk)
        completed_months.reverse() # Oldest to newest of the 4

        print(f"Seeding 4 completed months: {completed_months} and current month: {current_mk}")

        # Realistic expense templates
        expense_templates = [
            ("Grocery & Daily Essentials", "Food", "UPI", 1450),
            ("Electricity Bill", "Bills", "Net Banking", 2300),
            ("Cab to University Campus", "Travel", "UPI", 320),
            ("Casual Dining with Friends", "Food", "Debit/Credit Card", 1250),
            ("Monthly Mobile Recharge", "Bills", "UPI", 699),
            ("Textbooks & Stationery", "Other", "Cash", 850),
            ("Pharmacy & Medicine", "Health", "UPI", 480),
            ("Weekend Movie & Snacks", "Entertainment", "Debit/Credit Card", 750),
            ("Clothing & Apparel", "Shopping", "Debit/Credit Card", 2100),
            ("Vegetables & Fruits", "Food", "Cash", 520),
            ("Metro Smart Card Recharge", "Travel", "UPI", 500),
            ("Broadband Internet Bill", "Bills", "Net Banking", 999),
            ("Doctor Consultation", "Health", "Cash", 600),
            ("Online Course Subscription", "Other", "Debit/Credit Card", 1499),
        ]

        total_expenses_seeded = 0

        # Seed the 4 completed months
        monthly_budget_amount = 25000
        for m_idx, m_key in enumerate(completed_months):
            # Budget for each completed month
            budget_val = monthly_budget_amount + (m_idx * 1000)
            b = Budget(user_id=user.id, month=m_key, amount=budget_val)
            db.session.add(b)

            start_d, end_d = get_month_date_range(m_key)
            days_in_month = (end_d - start_d).days

            # 12 to 14 expenses per month
            for i, (desc, cat, mode, base_amt) in enumerate(expense_templates[:12 + (m_idx % 3)]):
                day_offset = (i * 2 + 1) % days_in_month
                exp_date = start_d + timedelta(days=day_offset)
                adj_amt = base_amt + (m_idx * 50) + ((i % 4) * 40)
                exp = Expense(
                    user_id=user.id,
                    amount=adj_amt,
                    category=cat,
                    payment_mode=mode,
                    description=desc,
                    expense_date=exp_date
                )
                db.session.add(exp)
                total_expenses_seeded += 1

        # Seed current month: Set budget to 30,000, and spending to ~76% (Warning status)
        current_budget_amount = 30000
        b_curr = Budget(user_id=user.id, month=current_mk, amount=current_budget_amount)
        db.session.add(b_curr)

        # Current month expenses (all dated <= today)
        curr_items = [
            ("Monthly Apartment Rent Share", "Bills", "Net Banking", 8500),
            ("Supermarket Monthly Grocery", "Food", "Debit/Credit Card", 4200),
            ("Electricity & Water Charges", "Bills", "UPI", 2150),
            ("Fuel / University Travel", "Travel", "UPI", 1850),
            ("Dining & Cafeteria", "Food", "Cash", 1650),
            ("Diagnostic Health Tests", "Health", "Debit/Credit Card", 1450),
            ("New Headphones & Cables", "Shopping", "Debit/Credit Card", 1999),
            ("Streaming & Gaming", "Entertainment", "UPI", 999)
        ]
        # Total = 8500+4200+2150+1850+1650+1450+1999+999 = 22,798 (~76% utilization -> Warning alert)

        start_curr, _ = get_month_date_range(current_mk)
        max_day = min(today.day, 28)
        for i, (desc, cat, mode, amt) in enumerate(curr_items):
            exp_day = max(1, (i * 3 + 1) % max_day)
            exp_date = date(today.year, today.month, exp_day)
            if exp_date > today:
                exp_date = today
            exp = Expense(
                user_id=user.id,
                amount=amt,
                category=cat,
                payment_mode=mode,
                description=desc,
                expense_date=exp_date
            )
            db.session.add(exp)
            total_expenses_seeded += 1

        db.session.commit()
        print(f"Successfully seeded {total_expenses_seeded} expenses across 5 months with budgets!")
        print("\n==========================================")
        print("  SMARTEXPENSE DEMO READY")
        print("==========================================")
        print(f"  Login URL : http://127.0.0.1:5000/login")
        print(f"  Email     : {demo_email}")
        print(f"  Password  : {demo_password}")
        print("==========================================\n")

if __name__ == '__main__':
    seed_demo_data()
