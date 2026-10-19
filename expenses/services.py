"""
Business-logic / service layer for expenses and categories.

All MongoDB interactions go through this module so views stay thin.
Amounts are stored as Decimal128 and converted to Python Decimal on read.
"""

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from bson import ObjectId
from bson.decimal128 import Decimal128

from .db import get_expenses_collection, get_categories_collection
from .validators import (
    validate_amount, validate_description, validate_category,
    validate_date, validate_payment_method, validate_notes,
    validate_category_name, validate_color,
)

# ──────────────────────────────── Default categories ──────────────────────────────

DEFAULT_CATEGORIES = [
    {'name': 'Food & Dining',    'color': '#f97316'},
    {'name': 'Transportation',   'color': '#3b82f6'},
    {'name': 'Shopping',         'color': '#ec4899'},
    {'name': 'Bills & Utilities','color': '#eab308'},
    {'name': 'Healthcare',       'color': '#22c55e'},
    {'name': 'Entertainment',    'color': '#a855f7'},
    {'name': 'Education',        'color': '#06b6d4'},
    {'name': 'Travel',           'color': '#14b8a6'},
    {'name': 'Other',            'color': '#6b7280'},
]


def _dec128_to_dec(val):
    """Convert Decimal128 → Python Decimal safely."""
    if isinstance(val, Decimal128):
        return Decimal(str(val))
    return Decimal(str(val)) if val is not None else Decimal('0')


def _enrich_expense(doc):
    """Add a Python-friendly `amount_dec` and string `id` to an expense doc."""
    if doc is None:
        return None
    doc['id'] = str(doc['_id'])
    doc['amount_dec'] = _dec128_to_dec(doc.get('amount', 0))
    doc['amount_display'] = f"{doc['amount_dec']:,.2f}"
    if isinstance(doc.get('date'), datetime):
        doc['date_str'] = doc['date'].strftime('%Y-%m-%d')
        doc['date_display'] = doc['date'].strftime('%b %d, %Y')
    else:
        doc['date_str'] = ''
        doc['date_display'] = ''
    return doc


# ──────────────────────────────── Category CRUD ────────────────────────────────

def ensure_default_categories(user_id):
    """Seed default categories for a new user (idempotent)."""
    col = get_categories_collection()
    for cat in DEFAULT_CATEGORIES:
        col.update_one(
            {'user_id': user_id, 'name': cat['name']},
            {'$setOnInsert': {
                'user_id': user_id,
                'name': cat['name'],
                'color': cat['color'],
                'is_default': True,
                'created_at': datetime.utcnow(),
            }},
            upsert=True,
        )


def get_user_categories(user_id):
    col = get_categories_collection()
    return list(col.find({'user_id': user_id}).sort('name', 1))


def get_category_names(user_id):
    return [c['name'] for c in get_user_categories(user_id)]


def add_category(user_id, name, color):
    name = validate_category_name(name)
    color = validate_color(color)
    col = get_categories_collection()
    # Check uniqueness
    if col.find_one({'user_id': user_id, 'name': name}):
        raise ValueError(f"Category '{name}' already exists.")
    col.insert_one({
        'user_id': user_id,
        'name': name,
        'color': color,
        'is_default': False,
        'created_at': datetime.utcnow(),
    })


def update_category(user_id, old_name, new_name, new_color):
    new_name = validate_category_name(new_name)
    new_color = validate_color(new_color)
    col = get_categories_collection()
    cat = col.find_one({'user_id': user_id, 'name': old_name})
    if not cat:
        raise ValueError("Category not found.")
    if new_name != old_name and col.find_one({'user_id': user_id, 'name': new_name}):
        raise ValueError(f"Category '{new_name}' already exists.")
    col.update_one(
        {'_id': cat['_id']},
        {'$set': {'name': new_name, 'color': new_color}},
    )
    # Rename category in all expenses
    if new_name != old_name:
        get_expenses_collection().update_many(
            {'user_id': user_id, 'category': old_name},
            {'$set': {'category': new_name}},
        )


def delete_category(user_id, name):
    expenses_col = get_expenses_collection()
    count = expenses_col.count_documents({'user_id': user_id, 'category': name})
    if count > 0:
        raise ValueError(
            f"Cannot delete '{name}' — {count} transaction(s) still use this category. "
            "Reassign them first."
        )
    col = get_categories_collection()
    result = col.delete_one({'user_id': user_id, 'name': name})
    if result.deleted_count == 0:
        raise ValueError("Category not found.")


def get_category_color_map(user_id):
    """Return {name: color} dict."""
    return {c['name']: c['color'] for c in get_user_categories(user_id)}


def get_category_spending(user_id, start_date=None, end_date=None):
    """Return list of {category, total, color} sorted by total desc."""
    match = {'user_id': user_id}
    if start_date or end_date:
        match['date'] = {}
        if start_date:
            match['date']['$gte'] = start_date
        if end_date:
            match['date']['$lte'] = end_date
        if not match['date']:
            del match['date']

    pipeline = [
        {'$match': match},
        {'$group': {'_id': '$category', 'total': {'$sum': {'$toDecimal': '$amount'}}}},
        {'$sort': {'total': -1}},
    ]
    results = list(get_expenses_collection().aggregate(pipeline))
    color_map = get_category_color_map(user_id)
    return [
        {
            'category': r['_id'],
            'total': Decimal(str(r['total'])),
            'color': color_map.get(r['_id'], '#6b7280'),
        }
        for r in results
    ]


# ──────────────────────────────── Expense CRUD ─────────────────────────────────

def create_expense(user_id, data):
    """Validate, store, and return the new expense dict."""
    cat_names = get_category_names(user_id)
    amount = validate_amount(data.get('amount'))
    description = validate_description(data.get('description'))
    category = validate_category(data.get('category'), cat_names)
    exp_date = validate_date(data.get('date'))
    payment_method = validate_payment_method(data.get('payment_method'))
    notes = validate_notes(data.get('notes'))

    now = datetime.utcnow()
    doc = {
        'user_id': user_id,
        'amount': Decimal128(str(amount)),
        'description': description,
        'category': category,
        'date': exp_date,
        'payment_method': payment_method,
        'notes': notes,
        'created_at': now,
        'updated_at': now,
    }
    get_expenses_collection().insert_one(doc)
    return _enrich_expense(doc)


def update_expense(user_id, expense_id, data):
    col = get_expenses_collection()
    existing = col.find_one({'_id': ObjectId(expense_id), 'user_id': user_id})
    if not existing:
        raise ValueError("Expense not found.")

    cat_names = get_category_names(user_id)
    amount = validate_amount(data.get('amount'))
    description = validate_description(data.get('description'))
    category = validate_category(data.get('category'), cat_names)
    exp_date = validate_date(data.get('date'))
    payment_method = validate_payment_method(data.get('payment_method'))
    notes = validate_notes(data.get('notes'))

    col.update_one(
        {'_id': ObjectId(expense_id)},
        {'$set': {
            'amount': Decimal128(str(amount)),
            'description': description,
            'category': category,
            'date': exp_date,
            'payment_method': payment_method,
            'notes': notes,
            'updated_at': datetime.utcnow(),
        }},
    )


def delete_expense(user_id, expense_id):
    result = get_expenses_collection().delete_one(
        {'_id': ObjectId(expense_id), 'user_id': user_id}
    )
    if result.deleted_count == 0:
        raise ValueError("Expense not found.")


def get_expense(user_id, expense_id):
    doc = get_expenses_collection().find_one(
        {'_id': ObjectId(expense_id), 'user_id': user_id}
    )
    return _enrich_expense(doc)


def list_expenses(user_id, *, search=None, category=None, payment_method=None,
                  start_date=None, end_date=None, sort_by='date', sort_dir=-1,
                  page=1, per_page=15):
    """Return (expenses_list, total_count, total_pages)."""
    query = {'user_id': user_id}
    if search:
        query['description'] = {'$regex': search, '$options': 'i'}
    if category:
        query['category'] = category
    if payment_method:
        query['payment_method'] = payment_method
    if start_date or end_date:
        query['date'] = {}
        if start_date:
            query['date']['$gte'] = start_date
        if end_date:
            query['date']['$lte'] = end_date
        if not query['date']:
            del query['date']

    col = get_expenses_collection()
    total = col.count_documents(query)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    cursor = (
        col.find(query)
        .sort(sort_by, sort_dir)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    expenses = [_enrich_expense(doc) for doc in cursor]
    return expenses, total, total_pages


# ──────────────────────────────── Dashboard stats ──────────────────────────────

def get_dashboard_stats(user_id, start_date=None, end_date=None):
    """Compute summary cards from MongoDB."""
    match = {'user_id': user_id}
    if start_date or end_date:
        match['date'] = {}
        if start_date:
            match['date']['$gte'] = start_date
        if end_date:
            match['date']['$lte'] = end_date
        if not match['date']:
            del match['date']

    col = get_expenses_collection()
    pipeline = [
        {'$match': match},
        {'$group': {
            '_id': None,
            'total': {'$sum': {'$toDecimal': '$amount'}},
            'count': {'$sum': 1},
            'min_date': {'$min': '$date'},
            'max_date': {'$max': '$date'},
        }},
    ]
    result = list(col.aggregate(pipeline))
    if not result:
        return {
            'total_expenses': Decimal('0'),
            'month_expenses': Decimal('0'),
            'avg_daily': Decimal('0'),
            'top_category': 'N/A',
            'top_category_amount': Decimal('0'),
            'total_count': 0,
            'month_change_pct': None,
        }

    r = result[0]
    total = Decimal(str(r['total']))
    count = r['count']
    min_d = r['min_date']
    max_d = r['max_date']

    # Days span
    if min_d and max_d and min_d != max_d:
        days = max((max_d - min_d).days, 1)
    else:
        days = 1
    avg_daily = (total / days).quantize(Decimal('0.01'))

    # This month
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_pipeline = [
        {'$match': {**{'user_id': user_id}, 'date': {'$gte': month_start}}},
        {'$group': {'_id': None, 'total': {'$sum': {'$toDecimal': '$amount'}}}},
    ]
    month_result = list(col.aggregate(month_pipeline))
    month_expenses = Decimal(str(month_result[0]['total'])) if month_result else Decimal('0')

    # Previous month
    prev_month_end = month_start - timedelta(seconds=1)
    prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_pipeline = [
        {'$match': {'user_id': user_id, 'date': {'$gte': prev_month_start, '$lte': prev_month_end}}},
        {'$group': {'_id': None, 'total': {'$sum': {'$toDecimal': '$amount'}}}},
    ]
    prev_result = list(col.aggregate(prev_pipeline))
    prev_month = Decimal(str(prev_result[0]['total'])) if prev_result else Decimal('0')

    if prev_month > 0:
        month_change_pct = ((month_expenses - prev_month) / prev_month * 100).quantize(Decimal('0.1'))
    else:
        month_change_pct = None

    # Top category
    cat_spending = get_category_spending(user_id, start_date, end_date)
    top_category = cat_spending[0]['category'] if cat_spending else 'N/A'
    top_category_amount = cat_spending[0]['total'] if cat_spending else Decimal('0')

    return {
        'total_expenses': total,
        'month_expenses': month_expenses,
        'avg_daily': avg_daily,
        'top_category': top_category,
        'top_category_amount': top_category_amount,
        'total_count': count,
        'month_change_pct': month_change_pct,
    }


def get_monthly_spending(user_id, year=None):
    """Return 12-element list of monthly totals for the given year."""
    if year is None:
        year = datetime.utcnow().year
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)
    pipeline = [
        {'$match': {'user_id': user_id, 'date': {'$gte': start, '$lte': end}}},
        {'$group': {
            '_id': {'$month': '$date'},
            'total': {'$sum': {'$toDecimal': '$amount'}},
        }},
    ]
    results = {r['_id']: Decimal(str(r['total'])) for r in get_expenses_collection().aggregate(pipeline)}
    return [float(results.get(m, 0)) for m in range(1, 13)]


def get_weekly_spending(user_id, start_date, end_date):
    """Return daily totals between start and end."""
    pipeline = [
        {'$match': {'user_id': user_id, 'date': {'$gte': start_date, '$lte': end_date}}},
        {'$group': {
            '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$date'}},
            'total': {'$sum': {'$toDecimal': '$amount'}},
        }},
        {'$sort': {'_id': 1}},
    ]
    results = list(get_expenses_collection().aggregate(pipeline))
    return [{'date': r['_id'], 'total': float(Decimal(str(r['total'])))} for r in results]


# ──────────────────────────────── CSV Import ───────────────────────────────────

def compute_fingerprint(user_id, date_str, description, amount_str):
    """Deterministic hash for deduplication."""
    raw = f"{user_id}|{date_str}|{description.strip().lower()}|{amount_str}"
    return hashlib.sha256(raw.encode()).hexdigest()


def import_csv_rows(user_id, rows):
    """
    Import validated rows. Returns (imported_count, skipped_duplicates).
    Each row is a dict with keys: date, description, amount, category, payment_method.
    """
    col = get_expenses_collection()
    cat_names = set(get_category_names(user_id))
    imported = 0
    skipped = 0
    now = datetime.utcnow()

    for row in rows:
        amount = validate_amount(row['amount'])
        description = validate_description(row['description'])
        date_val = validate_date(row['date'])
        payment_method = validate_payment_method(row.get('payment_method', 'Other'))
        category = row.get('category', 'Other').strip()
        if category not in cat_names:
            category = 'Other'

        fp = compute_fingerprint(user_id, date_val.strftime('%Y-%m-%d'), description, str(amount))

        # Try insert; skip on duplicate fingerprint
        try:
            col.insert_one({
                'user_id': user_id,
                'amount': Decimal128(str(amount)),
                'description': description,
                'category': category,
                'date': date_val,
                'payment_method': payment_method,
                'notes': '',
                'fingerprint': fp,
                'created_at': now,
                'updated_at': now,
            })
            imported += 1
        except Exception:
            skipped += 1

    return imported, skipped
