"""
MongoDB connection utility.

Provides a singleton MongoClient and convenience accessors for collections.
Connection parameters come from Django settings (which read env vars).
Indexes are created on first import.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.decimal128 import Decimal128
from django.conf import settings

_client = None


def get_client():
    """Return a cached MongoClient instance."""
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGODB_URI)
    return _client


def get_db():
    """Return the application database."""
    return get_client()[settings.MONGODB_DATABASE]


def get_expenses_collection():
    return get_db()['expenses']


def get_categories_collection():
    return get_db()['categories']


# --------------- Index creation ---------------

def ensure_indexes():
    """Create indexes for performance. Safe to call multiple times."""
    expenses = get_expenses_collection()
    expenses.create_index([('user_id', ASCENDING), ('date', DESCENDING)])
    expenses.create_index([('user_id', ASCENDING), ('category', ASCENDING)])

    # Drop old fingerprint index if it exists (was sparse, caused null conflicts)
    try:
        expenses.drop_index('user_id_1_fingerprint_1')
    except Exception:
        pass

    # Recreate with partialFilterExpression — only enforces uniqueness when
    # fingerprint exists AND is not null.  Manual expenses have no fingerprint.
    expenses.create_index(
        [('user_id', ASCENDING), ('fingerprint', ASCENDING)],
        unique=True,
        partialFilterExpression={'fingerprint': {'$type': 'string'}},
        name='user_fingerprint_unique',
    )

    categories = get_categories_collection()
    categories.create_index([('user_id', ASCENDING), ('name', ASCENDING)], unique=True)


# Create indexes when module is first loaded
try:
    ensure_indexes()
except Exception:
    # MongoDB might not be running yet during collectstatic / migrate
    pass

