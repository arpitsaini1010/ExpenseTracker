import os
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from flask import Flask, render_template, redirect, url_for, flash, request, abort, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import func

from config import Config
from models import db, User, Expense, Budget
from forms import RegistrationForm, LoginForm, ExpenseForm, BudgetForm, EmptyCsrfForm
from utils import (
    format_currency,
    format_inr_number,
    format_date_display,
    get_current_month_key,
    get_safe_month_key,
    get_month_date_range,
    get_effective_budget,
    calculate_budget_status,
    calculate_forecast,
    get_chart_window_months,
    get_payment_mode_analysis,
    validate_month_key
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Security headers to prevent sensitive financial data caching on authenticated pages (TC-07, NFR-SEC-06)
    @app.after_request
    def add_security_headers(response):
        if current_user.is_authenticated:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # Jinja filters and context processors
    @app.template_filter('inr')
    def filter_inr(value):
        return format_currency(value)

    @app.template_filter('inr_num')
    def filter_inr_num(value):
        return format_inr_number(value)

    @app.template_filter('date_fmt')
    def filter_date_fmt(value):
        return format_date_display(value)

    @app.template_filter('month_display')
    def filter_month_display(month_key):
        if not month_key or not validate_month_key(month_key):
            return month_key
        y, m = map(int, month_key.split('-'))
        return date(y, m, 1).strftime('%B %Y')

    @app.context_processor
    def inject_helpers():
        return {
            'empty_csrf_form': EmptyCsrfForm(),
            'current_year': date.today().year,
            'today_date': date.today(),
            'current_month_key': get_current_month_key()
        }

    # Helper: validate safe redirect URL (FR-AUTH-08, NFR-SEC-08)
    def is_safe_url(target):
        if not target:
            return False
        # Block backslash bypasses and protocol-relative URLs (e.g. //evil.com or /\evil.com)
        clean = target.replace('\\', '/')
        if clean.startswith('//') or clean.startswith('///'):
            return False
        ref_url = urlsplit(request.host_url)
        test_url = urlsplit(clean)
        if test_url.scheme not in ('', 'http', 'https'):
            return False
        if test_url.netloc and test_url.netloc != ref_url.netloc:
            return False
        return True

    # --- Routes ---

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, 'static', 'img'),
            'favicon.svg',
            mimetype='image/svg+xml'
        )

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                name=form.name.data.strip(),
                email=form.email.data.strip().lower()
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login', email=user.email))

        return render_template('register.html', form=form)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = LoginForm()
        if form.validate_on_submit():
            email_clean = form.email.data.strip().lower()
            user = User.query.filter_by(email=email_clean).first()
            if user and user.check_password(form.password.data):
                login_user(user)
                next_page = request.args.get('next')
                if next_page and is_safe_url(next_page):
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            flash('Invalid email or password', 'danger')

        return render_template('login.html', form=form)

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        if request.method == 'POST':
            if current_user.is_authenticated:
                logout_user()
            flash('You have been logged out.', 'info')
            return redirect(url_for('login'))
        # If someone visits GET /logout directly, safely redirect to login
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        selected_month = get_safe_month_key(request.args.get('month'))
        start_date, next_month_start = get_month_date_range(selected_month)

        # 1. Total spent all time (SQL aggregate query, NFR-PRF-02)
        total_spent_all_time = db.session.query(func.sum(Expense.amount))\
            .filter(Expense.user_id == current_user.id).scalar() or 0

        # Check if user has any expenses (FR-DSH-09)
        total_expense_count = db.session.query(func.count(Expense.id))\
            .filter(Expense.user_id == current_user.id).scalar() or 0
        has_any_expenses = (total_expense_count > 0)

        # 2. Expenses for selected month (SQL aggregate query, NFR-PRF-02)
        spent_this_month = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            Expense.expense_date >= start_date,
            Expense.expense_date < next_month_start
        ).scalar() or 0
        has_month_expenses = (spent_this_month > 0)

        # 3. Effective budget
        eff_budget = get_effective_budget(current_user.id, selected_month)

        # 4. Budget status and alerts
        budget_status = calculate_budget_status(spent_this_month, eff_budget)

        # 5. Forecast (FR-FOR)
        forecast_data = calculate_forecast(current_user.id)

        # 6. Month selector options (months with expenses + current month)
        distinct_months_tuples = db.session.query(
            func.strftime('%Y-%m', Expense.expense_date)
        ).filter(Expense.user_id == current_user.id).distinct().all()
        
        available_months = set(t[0] for t in distinct_months_tuples if t[0])
        available_months.add(get_current_month_key())
        available_months.add(selected_month)
        sorted_months = sorted(list(available_months), reverse=True)

        # 7. Category-wise chart data (SQL aggregate query, NFR-PRF-02)
        cat_rows = db.session.query(
            Expense.category,
            func.sum(Expense.amount).label('tot')
        ).filter(
            Expense.user_id == current_user.id,
            Expense.expense_date >= start_date,
            Expense.expense_date < next_month_start
        ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

        cat_labels = [r[0] for r in cat_rows]
        cat_values = [int(r[1]) for r in cat_rows]

        # 8. Month-wise chart data (6-month bar chart ending with selected month)
        window_keys, window_labels = get_chart_window_months(selected_month, Config.CHART_MONTHS)
        
        # Query spend per month for these 6 months
        window_spends = {mk: 0 for mk in window_keys}
        if window_keys:
            w_start, _ = get_month_date_range(window_keys[0])
            _, w_end = get_month_date_range(window_keys[-1])
            window_query = db.session.query(
                func.strftime('%Y-%m', Expense.expense_date).label('mk'),
                func.sum(Expense.amount).label('tot')
            ).filter(
                Expense.user_id == current_user.id,
                Expense.expense_date >= w_start,
                Expense.expense_date < w_end
            ).group_by('mk').all()

            for row in window_query:
                if row.mk in window_spends:
                    window_spends[row.mk] = int(row.tot)

        month_chart_values = [window_spends[mk] for mk in window_keys]

        # 9. Payment mode analysis (SQL aggregate query, NFR-PRF-02, FR-PAY)
        pay_rows = db.session.query(
            Expense.payment_mode,
            func.sum(Expense.amount).label('tot')
        ).filter(
            Expense.user_id == current_user.id,
            Expense.expense_date >= start_date,
            Expense.expense_date < next_month_start
        ).group_by(Expense.payment_mode).all()

        payment_dict = {mode: 0 for mode in Config.PAYMENT_MODES}
        for r in pay_rows:
            if r[0] in payment_dict:
                payment_dict[r[0]] = int(r[1])

        payment_mode_data = get_payment_mode_analysis(payment_dict, spent_this_month)
        pay_labels = [item['mode'] for item in payment_mode_data]
        pay_values = [item['amount'] for item in payment_mode_data]

        # 10. Recent Transactions (latest 5 across all months, FR-DSH-07)
        recent_transactions = Expense.query.filter_by(user_id=current_user.id)\
            .order_by(Expense.expense_date.desc(), Expense.id.desc())\
            .limit(Config.RECENT_COUNT).all()

        return render_template(
            'dashboard.html',
            selected_month=selected_month,
            sorted_months=sorted_months,
            total_spent_all_time=total_spent_all_time,
            spent_this_month=spent_this_month,
            eff_budget=eff_budget,
            budget_status=budget_status,
            forecast_data=forecast_data,
            has_any_expenses=has_any_expenses,
            has_month_expenses=has_month_expenses,
            cat_labels=cat_labels,
            cat_values=cat_values,
            month_chart_labels=window_labels,
            month_chart_values=month_chart_values,
            payment_mode_data=payment_mode_data,
            pay_labels=pay_labels,
            pay_values=pay_values,
            recent_transactions=recent_transactions
        )

    @app.route('/expenses')
    @login_required
    def expenses():
        selected_month = get_safe_month_key(request.args.get('month'))
        start_date, next_month_start = get_month_date_range(selected_month)

        expense_list = Expense.query.filter(
            Expense.user_id == current_user.id,
            Expense.expense_date >= start_date,
            Expense.expense_date < next_month_start
        ).order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

        month_total = sum(e.amount for e in expense_list)

        # Available months for selector
        distinct_months = db.session.query(
            func.strftime('%Y-%m', Expense.expense_date)
        ).filter(Expense.user_id == current_user.id).distinct().all()
        
        available_months = set(t[0] for t in distinct_months if t[0])
        available_months.add(get_current_month_key())
        available_months.add(selected_month)
        sorted_months = sorted(list(available_months), reverse=True)

        return render_template(
            'expenses.html',
            selected_month=selected_month,
            sorted_months=sorted_months,
            expenses=expense_list,
            month_total=month_total
        )

    @app.route('/expenses/add', methods=['GET', 'POST'])
    @login_required
    def add_expense():
        form = ExpenseForm()
        if form.validate_on_submit():
            desc = (form.description.data or '').strip()
            expense = Expense(
                user_id=current_user.id,
                amount=form.amount.data,
                category=form.category.data,
                description=desc if desc else None,
                expense_date=form.expense_date.data,
                payment_mode=form.payment_mode.data
            )
            db.session.add(expense)
            db.session.commit()

            expense_month = expense.expense_date.strftime('%Y-%m')
            flash(f'Expense of ₹{format_inr_number(expense.amount)} added successfully.', 'success')

            # FR-ALR-08: Flash alert if month's status is Warning or worse
            eff_budget = get_effective_budget(current_user.id, expense_month)
            if eff_budget is not None:
                start_d, end_d = get_month_date_range(expense_month)
                m_spent = db.session.query(func.sum(Expense.amount)).filter(
                    Expense.user_id == current_user.id,
                    Expense.expense_date >= start_d,
                    Expense.expense_date < end_d
                ).scalar() or 0
                status_info = calculate_budget_status(m_spent, eff_budget)
                if status_info['status'] in ('Warning', 'Critical', 'Over Budget'):
                    flash(status_info['banner_message'], status_info['color'])

            return redirect(url_for('expenses', month=expense_month))

        return render_template('expense_form.html', form=form, title='Add Expense', is_edit=False)

    @app.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_expense(expense_id):
        expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
        form = ExpenseForm(obj=expense)

        if form.validate_on_submit():
            desc = (form.description.data or '').strip()
            expense.amount = form.amount.data
            expense.category = form.category.data
            expense.description = desc if desc else None
            expense.expense_date = form.expense_date.data
            expense.payment_mode = form.payment_mode.data
            db.session.commit()

            expense_month = expense.expense_date.strftime('%Y-%m')
            flash('Expense updated successfully.', 'success')

            # FR-ALR-08: Flash alert if month's status is Warning or worse
            eff_budget = get_effective_budget(current_user.id, expense_month)
            if eff_budget is not None:
                start_d, end_d = get_month_date_range(expense_month)
                m_spent = db.session.query(func.sum(Expense.amount)).filter(
                    Expense.user_id == current_user.id,
                    Expense.expense_date >= start_d,
                    Expense.expense_date < end_d
                ).scalar() or 0
                status_info = calculate_budget_status(m_spent, eff_budget)
                if status_info['status'] in ('Warning', 'Critical', 'Over Budget'):
                    flash(status_info['banner_message'], status_info['color'])

            return redirect(url_for('expenses', month=expense_month))

        return render_template('expense_form.html', form=form, title='Edit Expense', is_edit=True, expense=expense)

    @app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
    @login_required
    def delete_expense(expense_id):
        expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
        month_key = expense.expense_date.strftime('%Y-%m')
        
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully.', 'success')
        return redirect(url_for('expenses', month=month_key))

    @app.route('/budget', methods=['GET', 'POST'])
    @login_required
    def budget():
        selected_month = get_safe_month_key(request.args.get('month'))
        form = BudgetForm()

        if form.validate_on_submit():
            target_month = form.month.data.strip()
            if not validate_month_key(target_month):
                flash('Invalid month format. Please select a valid month.', 'danger')
                return redirect(url_for('budget', month=selected_month))

            existing_budget = Budget.query.filter_by(
                user_id=current_user.id,
                month=target_month
            ).first()

            if existing_budget:
                existing_budget.amount = form.amount.data
                existing_budget.updated_at = datetime.now(timezone.utc)
            else:
                new_budget = Budget(
                    user_id=current_user.id,
                    month=target_month,
                    amount=form.amount.data
                )
                db.session.add(new_budget)

            db.session.commit()
            flash(f'Budget of ₹{format_inr_number(form.amount.data)} saved for {target_month}.', 'success')
            return redirect(url_for('budget', month=target_month))

        # Effective budget for the chosen month
        eff_budget = get_effective_budget(current_user.id, selected_month)

        # Stored budget record specifically for this month (if any)
        stored_budget = Budget.query.filter_by(
            user_id=current_user.id,
            month=selected_month
        ).first()

        # Pre-fill form amount if this month has a stored budget
        if request.method == 'GET' and stored_budget:
            form.amount.data = stored_budget.amount

        # All budgets set by user, newest first (FR-BUD-04)
        user_budgets = Budget.query.filter_by(user_id=current_user.id)\
            .order_by(Budget.month.desc()).all()

        return render_template(
            'budget.html',
            form=form,
            selected_month=selected_month,
            eff_budget=eff_budget,
            stored_budget=stored_budget,
            user_budgets=user_budgets
        )

    # --- Error Handlers (NFR-REL-03, NFR-USE-03) ---
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template('400.html', description=f"Security token error: {error.description}"), 400

    @app.errorhandler(400)
    def bad_request_error(error):
        return render_template('400.html', description="Bad request. The server could not understand the request."), 400

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(405)
    def method_not_allowed_error(error):
        return render_template('405.html'), 405

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f"Internal 500 error: {error}", exc_info=True)
        return render_template('500.html'), 500

    # Ensure tables are created
    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    # Debug mode is enabled by default for local development (can be disabled via FLASK_DEBUG=False)
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1')
    app.run(debug=debug_mode, host='127.0.0.1', port=5000)
