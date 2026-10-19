"""
Validation helpers for expense data.

All validators raise ValueError with a user-friendly message on failure.
"""

import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

PAYMENT_METHODS = ['Cash', 'Credit Card', 'Debit Card', 'UPI', 'Net Banking', 'Wallet', 'Other']


def validate_amount(value):
    """Return a Decimal if *value* represents a positive monetary amount."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Amount must be a valid number.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if amount > Decimal('99999999.99'):
        raise ValueError("Amount is unreasonably large.")
    # Round to 2 decimal places
    return amount.quantize(Decimal('0.01'))


def validate_description(value):
    if not value or not str(value).strip():
        raise ValueError("Description is required.")
    desc = str(value).strip()
    if len(desc) > 500:
        raise ValueError("Description must be 500 characters or fewer.")
    return desc


def validate_category(value, valid_categories):
    if not value or not str(value).strip():
        raise ValueError("Category is required.")
    cat = str(value).strip()
    if cat not in valid_categories:
        raise ValueError(f"Invalid category: {cat}")
    return cat


def validate_date(value):
    """Accept YYYY-MM-DD string or date/datetime objects. Return a datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d')
    except (ValueError, TypeError):
        raise ValueError("Date must be in YYYY-MM-DD format.")


def validate_payment_method(value):
    if not value or not str(value).strip():
        raise ValueError("Payment method is required.")
    pm = str(value).strip()
    if pm not in PAYMENT_METHODS:
        raise ValueError(f"Invalid payment method: {pm}")
    return pm


def validate_notes(value):
    if value is None:
        return ''
    notes = str(value).strip()
    if len(notes) > 1000:
        raise ValueError("Notes must be 1000 characters or fewer.")
    return notes


def validate_category_name(value):
    if not value or not str(value).strip():
        raise ValueError("Category name is required.")
    name = str(value).strip()
    if len(name) > 100:
        raise ValueError("Category name must be 100 characters or fewer.")
    if not re.match(r'^[A-Za-z0-9 &\-]+$', name):
        raise ValueError("Category name may contain only letters, numbers, spaces, '&', and '-'.")
    return name


def validate_color(value):
    if not value or not str(value).strip():
        return '#6366f1'  # default indigo
    color = str(value).strip()
    if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
        raise ValueError("Color must be a valid hex code like #6366f1.")
    return color
