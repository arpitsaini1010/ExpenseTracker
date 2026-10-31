from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, SelectField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange, Optional, ValidationError
from config import Config
from models import User

class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[
        DataRequired(message="Name is required.")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required."),
        Length(max=120, message="Email must be at most 120 characters.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required."),
        Length(min=Config.PASSWORD_MIN, max=128, message=f"Password must be at least {Config.PASSWORD_MIN} characters.")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password."),
        EqualTo('password', message="Passwords do not match.")
    ])
    submit = SubmitField('Register')

    def validate_name(self, field):
        trimmed = (field.data or '').strip()
        if len(trimmed) < 2 or len(trimmed) > 80:
            raise ValidationError("Name must be between 2 and 80 characters.")

    def validate_email(self, field):
        lower_email = field.data.strip().lower()
        import re
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', lower_email):
            raise ValidationError("Please enter a valid email address.")
        if User.query.filter_by(email=lower_email).first():
            raise ValidationError("This email is already registered")


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required.")
    ])
    submit = SubmitField('Login')


class ExpenseForm(FlaskForm):
    amount = IntegerField('Amount (₹)', validators=[
        DataRequired(message="Amount is required and must be a whole number."),
        NumberRange(min=1, max=Config.MAX_EXPENSE, message=f"Amount must be between 1 and {Config.MAX_EXPENSE:,}.")
    ])
    category = SelectField('Category', validators=[
        DataRequired(message="Category is required.")
    ], choices=Config.CATEGORIES)
    description = StringField('Description (Optional)')
    expense_date = DateField('Expense Date', format='%Y-%m-%d', default=date.today, validators=[
        DataRequired(message="Date is required.")
    ])
    payment_mode = SelectField('Payment Mode', validators=[
        DataRequired(message="Payment mode is required.")
    ], choices=Config.PAYMENT_MODES)
    submit = SubmitField('Save Expense')

    def validate_category(self, field):
        if field.data not in Config.CATEGORIES:
            raise ValidationError("Invalid category selected.")

    def validate_payment_mode(self, field):
        if field.data not in Config.PAYMENT_MODES:
            raise ValidationError("Invalid payment mode selected.")

    def validate_description(self, field):
        if field.data:
            trimmed = field.data.strip()
            if len(trimmed) > Config.DESCRIPTION_MAX:
                raise ValidationError(f"Description must be at most {Config.DESCRIPTION_MAX} characters.")

    def validate_expense_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("Expense date cannot be in the future.")


class BudgetForm(FlaskForm):
    month = StringField('Month', validators=[
        DataRequired(message="Month is required.")
    ])
    amount = IntegerField('Monthly Budget (₹)', validators=[
        DataRequired(message="Budget amount is required and must be a whole number."),
        NumberRange(min=1, max=Config.MAX_BUDGET, message=f"Budget must be between 1 and {Config.MAX_BUDGET:,}.")
    ])
    submit = SubmitField('Save Budget')

    def validate_month(self, field):
        import re
        val = (field.data or '').strip()
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', val):
            raise ValidationError("Invalid month format. Please select a valid month (YYYY-MM).")


class EmptyCsrfForm(FlaskForm):
    """Simple form for CSRF-protected POST actions like logout and delete."""
    pass
