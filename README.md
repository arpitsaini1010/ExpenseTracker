# SmartExpense: Smart Expense & Financial Insight System

**Version 1.0 (Academic Project Baseline)**  
*School of Computer Applications, Career Point University, Kota*  
- **Author:** Muskan Rajpal (KID: `K25162`, BCA-V Semester)  
- **Project Supervisor:** Mr. Parveen Kr. Goyal  
- **Technology Stack:** Python 3, Flask, SQLite, SQLAlchemy ORM, HTML5, Bootstrap 5, JavaScript, Chart.js  

---

## 📌 Project Overview
**SmartExpense** is a secure, web-based personal finance management application that empowers users to record daily expenses, set monthly spending limits, monitor budget utilization in real-time, and view automated spending forecasts.

### Core Objectives
1. **Centralized Expense Tracking:** Record expenditures with whole-rupee amounts, category, transaction date (no future dates), payment mode, and optional descriptions.
2. **Real-Time Budget Monitoring:** Track live spending against monthly budgets with automated boundary-based alerts (**Normal**, **Warning**, **Critical**, **Over Budget**).
3. **Visual Financial Analytics:** Interactive charts powered by Chart.js:
   - Category Breakdown (doughnut chart, sorted by expenditure)
   - 6-Month Spending Trend (bar chart for the past 6 calendar months)
   - Payment Mode Analysis (doughnut chart and detailed share table across Cash, UPI, Card, Net Banking)
4. **Reliable Next-Month Forecasting:** Transparent arithmetic average of past completed months (excluding current month in progress) with budget comparisons.
5. **Private Data Isolation & Security:** Strong user authentication with salted Werkzeug password hashes, CSRF protection, and strict ownership filtering on all queries.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure Python 3.10+ is installed on your system.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Seed Demo Data (Optional but Recommended for Viva & Evaluation)
Populate the database with a demonstration user and 5 months of realistic expenses and budgets:
```bash
python seed.py
```
**Demo Login Credentials:**
- **Email:** `demo@smartexpense.com`
- **Password:** `Password123`

### 4. Run the Web Application
```bash
python app.py
```
Access the application in your browser at:  
👉 **http://127.0.0.1:5000**

---

## 🧪 Running Automated Acceptance Tests
The test suite implements the acceptance tests specified in **Appendix C** of the SRS:
```bash
python -m pytest tests/
```
All 28 acceptance tests verify:
- User registration validations, case-insensitive email uniqueness, and password hashing.
- Authentication guards and 404 data isolation between users.
- Whole-rupee validations (1 to 1,000,000) and future-date restrictions.
- Budget upserting and month-to-month budget inheritance.
- Integer threshold calculations at 70%, 90%, and 100% boundary amounts.
- Forecast calculation (completed months only, skipping empty months, rounding half up).
- Category and payment mode breakdowns and responsive UI.

---

## 📂 Project Architecture

```
Muskan Project/
├── app.py                # Application factory, routes, and error handlers
├── config.py             # System constants, categories, payment modes, thresholds
├── models.py             # SQLAlchemy models: User, Expense, Budget
├── forms.py              # WTForms forms with validation and CSRF protection
├── utils.py              # Business rules (BR-01 to BR-08), INR formatting, forecast logic
├── seed.py               # Demo database seeder script
├── requirements.txt      # Python dependencies list
├── README.md             # Project documentation and guide
├── templates/            # HTML templates extending base.html
│   ├── base.html         # Responsive navbar, flash alerts, and footer
│   ├── login.html        # User sign-in page with demo credentials box
│   ├── register.html     # User registration page
│   ├── dashboard.html    # Full analytical dashboard with cards & Chart.js
│   ├── expenses.html     # Monthly expense record with edit/delete actions
│   ├── expense_form.html # Add and edit expense form
│   ├── budget.html       # Monthly budget setting and inheritance history
│   ├── 404.html          # Custom 404 Not Found error page
│   └── 500.html          # Custom 500 Server Error page
├── static/
│   ├── css/
│   │   └── style.css     # Premium custom CSS, gradients, and category tags
│   └── js/
│       └── dashboard.js  # Dynamic Chart.js visualizations
└── tests/
    └── test_smartexpense.py # Automated acceptance test suite
```

---

## 💡 Key Business Rules & Formulas

| Feature | Rule & Formula |
| :--- | :--- |
| **Effective Budget** | Uses budget explicitly set for month; falls back to the latest earlier set budget; `None` if never set. |
| **Utilization %** | `(Spent * 100) // Effective Budget` (integer arithmetic rounded down). Visual bar capped at 100%. |
| **Status Alert** | `< 70%`: Normal (Green) <br> `70% - 89%`: Warning (Yellow) <br> `90% - 99%`: Critical (Red) <br> `≥ 100%`: Over Budget (Dark) |
| **Forecast** | Arithmetic mean of monthly totals for completed months strictly before current month. Empty months are ignored. |
| **Indian Currency** | Formatted with Indian commas (e.g., `₹1,23,456`). |
