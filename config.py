import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smartexpense-academic-baseline-secret-key-2026')

    # Database configuration (support Render DATABASE_URL & auto-fix postgres:// scheme)
    _db_url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI', 'sqlite:///smartexpense.db')
    if _db_url and _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Session & Cookie Security (NFR-SEC-06)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')

    # Categories (FR-CAT-01, Appendix B)
    CATEGORIES = [
        'Food',
        'Travel',
        'Bills',
        'Shopping',
        'Health',
        'Entertainment',
        'Other'
    ]

    # Payment Modes (FR-CAT-02, Appendix B)
    PAYMENT_MODES = [
        'Cash',
        'UPI',
        'Debit/Credit Card',
        'Net Banking'
    ]

    # Limits and Thresholds (Appendix B)
    MAX_EXPENSE = 1_000_000
    MAX_BUDGET = 10_000_000
    WARNING_PCT = 70
    CRITICAL_PCT = 90
    OVER_PCT = 100
    CHART_MONTHS = 6
    RECENT_COUNT = 5
    DESCRIPTION_MAX = 200
    PASSWORD_MIN = 8
