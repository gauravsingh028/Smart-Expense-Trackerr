"""
MongoDB-backed session engine for Django.

Stores session data in the MongoDB 'sessions' collection instead of SQLite,
allowing the app to run on read-only filesystems like Vercel serverless.
"""

import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.sessions.backends.base import (
    CreateError,
    SessionBase,
    UpdateError,
)

from expenses.db import get_db


def get_sessions_collection():
    """Return the MongoDB sessions collection."""
    return get_db()['django_sessions']


class SessionStore(SessionBase):
    """Django session backend using MongoDB."""

    def __init__(self, session_key=None):
        super().__init__(session_key)

    def _get_collection(self):
        return get_sessions_collection()

    def load(self):
        try:
            doc = self._get_collection().find_one({
                '_id': self.session_key,
                'expire_date': {'$gt': datetime.utcnow()},
            })
            if doc:
                return self.decode(doc['session_data'])
        except Exception:
            pass
        self._session_key = None
        return {}

    def exists(self, session_key):
        return self._get_collection().find_one({'_id': session_key}) is not None

    def create(self):
        while True:
            self._session_key = self._get_new_session_key()
            try:
                self.save(must_create=True)
            except CreateError:
                continue
            self.modified = True
            return

    def save(self, must_create=False):
        if self.session_key is None:
            return self.create()

        data = self._get_session(no_load=must_create)
        session_data = self.encode(data)
        expire_date = datetime.utcnow() + timedelta(seconds=settings.SESSION_COOKIE_AGE)

        doc = {
            '_id': self.session_key,
            'session_data': session_data,
            'expire_date': expire_date,
        }

        coll = self._get_collection()
        if must_create:
            try:
                coll.insert_one(doc)
            except Exception:
                raise CreateError()
        else:
            coll.replace_one({'_id': self.session_key}, doc, upsert=True)

    def delete(self, session_key=None):
        if session_key is None:
            if self.session_key is None:
                return
            session_key = self.session_key
        self._get_collection().delete_one({'_id': session_key})

    @classmethod
    def clear_expired(cls):
        get_sessions_collection().delete_many({
            'expire_date': {'$lte': datetime.utcnow()},
        })


# Ensure TTL index for auto-cleanup
try:
    coll = get_sessions_collection()
    coll.create_index('expire_date', expireAfterSeconds=0)
except Exception:
    pass
