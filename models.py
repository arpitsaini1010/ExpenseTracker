from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, event
from sqlalchemy.engine import Engine

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if type(dbapi_connection).__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    # Relationships
    expenses = db.relationship('Expense', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    budgets = db.relationship('Budget', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class Expense(db.Model):
    __tablename__ = 'expenses'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_expenses_amount_positive'),
        Index('ix_expenses_user_date', 'user_id', 'expense_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    expense_date = db.Column(db.Date, nullable=False)
    payment_mode = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def __repr__(self):
        return f'<Expense {self.id} ₹{self.amount} {self.category} on {self.expense_date}>'


class Budget(db.Model):
    __tablename__ = 'budgets'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_budgets_amount_positive'),
        UniqueConstraint('user_id', 'month', name='uq_budgets_user_month'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # Format YYYY-MM
    amount = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f'<Budget {self.month}: ₹{self.amount}>'
