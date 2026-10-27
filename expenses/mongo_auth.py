"""
MongoDB-backed authentication backend and user model.

Replaces Django's default SQLite-backed auth with MongoDB so the app
can run on read-only filesystems like Vercel serverless.
"""

import hashlib
import hmac
import secrets
from datetime import datetime

from bson import ObjectId

from .db import get_db


def get_users_collection():
    """Return the MongoDB users collection."""
    return get_db()['users']


# ──────────────────────── Password hashing ────────────────────────

def _hash_password(password, salt=None):
    """Hash a password with PBKDF2-SHA256. Returns 'salt$hash'."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260_000)
    return f"{salt}${dk.hex()}"


def _check_password(password, stored):
    """Verify a password against a stored 'salt$hash' string."""
    if not stored or '$' not in stored:
        return False
    salt, _ = stored.split('$', 1)
    return hmac.compare_digest(_hash_password(password, salt), stored)


# ──────────────────────── Mock Meta (for Django login()) ──────────

class _MockPk:
    """Mimics Django's model field pk so login() can call _meta.pk.value_to_string(user)."""

    def value_to_string(self, user):
        return str(user.pk)


class _MockMeta:
    pk = _MockPk()
    app_label = 'expenses'


# ──────────────────────── MongoUser (duck-types Django User) ──────

class MongoUser:
    """
    Lightweight user object that quacks like Django's User model
    just enough for templates, login(), @login_required, and signals.
    """

    backend = 'expenses.mongo_auth.MongoAuthBackend'
    _meta = _MockMeta()

    def __init__(self, user_doc):
        self._doc = user_doc
        self.pk = str(user_doc['_id'])
        self.id = str(user_doc['_id'])
        self.username = user_doc.get('username', '')
        self.email = user_doc.get('email', '')
        self.first_name = user_doc.get('first_name', '')
        self.last_name = user_doc.get('last_name', '')
        self.is_active = user_doc.get('is_active', True)
        self.is_staff = False
        self.is_superuser = False
        self.last_login = user_doc.get('last_login')

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_username(self):
        return self.username

    def get_session_auth_hash(self):
        """Return a hash for session validation (Django checks this)."""
        key = self._doc.get('password', '') + self.pk
        return hashlib.sha256(key.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        """
        Django's user_logged_in signal calls user.save(update_fields=['last_login']).
        We handle this by updating MongoDB directly.
        """
        update_fields = kwargs.get('update_fields', None)
        if update_fields:
            update = {}
            for field in update_fields:
                update[field] = getattr(self, field, None)
            if update:
                get_users_collection().update_one(
                    {'_id': ObjectId(self.pk)},
                    {'$set': update},
                )
        else:
            # Full save — update all mutable fields
            get_users_collection().update_one(
                {'_id': ObjectId(self.pk)},
                {'$set': {
                    'username': self.username,
                    'email': self.email,
                    'first_name': self.first_name,
                    'last_name': self.last_name,
                    'last_login': self.last_login,
                    'is_active': self.is_active,
                }},
            )

    def __str__(self):
        return self.username


# ──────────────────────── Authentication backend ──────────────────

class MongoAuthBackend:
    """
    Django authentication backend that stores users in MongoDB.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        users = get_users_collection()
        user_doc = users.find_one({'username': username})
        if user_doc is None:
            return None
        if not _check_password(password, user_doc.get('password', '')):
            return None
        if not user_doc.get('is_active', True):
            return None
        # Update last_login
        users.update_one({'_id': user_doc['_id']}, {'$set': {'last_login': datetime.utcnow()}})
        return MongoUser(user_doc)

    def get_user(self, user_id):
        """Called by Django's session framework to reload user from session."""
        users = get_users_collection()
        try:
            user_doc = users.find_one({'_id': ObjectId(user_id)})
        except Exception:
            return None
        if user_doc is None:
            return None
        return MongoUser(user_doc)


# ──────────────────────── Helper functions ────────────────────────

def create_user(username, email, password, first_name='', last_name=''):
    """Create a new user in MongoDB. Returns MongoUser."""
    users = get_users_collection()
    doc = {
        'username': username,
        'email': email,
        'password': _hash_password(password),
        'first_name': first_name,
        'last_name': last_name,
        'is_active': True,
        'date_joined': datetime.utcnow(),
        'last_login': None,
    }
    result = users.insert_one(doc)
    doc['_id'] = result.inserted_id
    return MongoUser(doc)


def user_exists(username=None, email=None):
    """Check if a user with the given username or email already exists."""
    users = get_users_collection()
    if username:
        if users.find_one({'username': username}):
            return True
    if email:
        if users.find_one({'email': email}):
            return True
    return False


def ensure_user_indexes():
    """Create indexes on the users collection."""
    users = get_users_collection()
    users.create_index('username', unique=True)
    users.create_index('email', unique=True)


# Create indexes on first import
try:
    ensure_user_indexes()
except Exception:
    pass
