"""
Custom authentication middleware for MongoDB-backed users.

Replaces Django's built-in AuthenticationMiddleware because Django's
default middleware calls get_user_model()._meta.pk.to_python() which
expects an integer primary key. Our MongoDB users have string ObjectId PKs.
"""

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib import auth
from django.utils.functional import SimpleLazyObject

SESSION_KEY = '_auth_user_id'
BACKEND_SESSION_KEY = '_auth_user_backend'
HASH_SESSION_KEY = '_auth_user_hash'


def get_user(request):
    """
    Load user from session using our MongoDB auth backend directly,
    bypassing Django's to_python() integer validation.
    """
    if not hasattr(request, '_cached_user'):
        user = _load_user_from_session(request)
        request._cached_user = user
    return request._cached_user


def _load_user_from_session(request):
    """Read user ID from session and load via our MongoAuthBackend."""
    user_id = request.session.get(SESSION_KEY)
    backend_path = request.session.get(BACKEND_SESSION_KEY)

    if user_id is None or backend_path is None:
        return AnonymousUser()

    # Load the backend
    try:
        backend = auth.load_backend(backend_path)
    except ImportError:
        return AnonymousUser()

    # Load user from backend
    user = backend.get_user(user_id)
    if user is None:
        return AnonymousUser()

    # Verify session auth hash (security check)
    session_hash = request.session.get(HASH_SESSION_KEY, '')
    if hasattr(user, 'get_session_auth_hash'):
        session_auth_hash = user.get_session_auth_hash()
        if session_hash and not _constant_time_compare(session_hash, session_auth_hash):
            # Hash mismatch — session is invalid
            request.session.flush()
            return AnonymousUser()

    return user


def _constant_time_compare(val1, val2):
    """Constant-time string comparison."""
    import hmac
    return hmac.compare_digest(val1, val2)


class MongoAuthMiddleware:
    """
    Middleware that sets request.user using our MongoDB backend.
    Drop-in replacement for django.contrib.auth.middleware.AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: get_user(request))
        return self.get_response(request)
