"""
Tests for the expense tracker application.

Run: python manage.py test expenses
"""

from datetime import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User


class AuthTestCase(TestCase):
    """Test registration, login, logout."""

    def setUp(self):
        self.client = Client()

    def test_register_page_loads(self):
        resp = self.client.get('/auth/register/')
        self.assertEqual(resp.status_code, 200)

    def test_login_page_loads(self):
        resp = self.client.get('/auth/login/')
        self.assertEqual(resp.status_code, 200)

    def test_register_creates_user(self):
        resp = self.client.post('/auth/register/', {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'first_name': 'Test',
            'last_name': 'User',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_register_password_mismatch(self):
        resp = self.client.post('/auth/register/', {
            'username': 'testuser2',
            'email': 'test2@example.com',
            'password1': 'SecurePass123',
            'password2': 'DifferentPass',
        })
        self.assertEqual(resp.status_code, 200)  # stays on page
        self.assertFalse(User.objects.filter(username='testuser2').exists())

    def test_login_success(self):
        User.objects.create_user('loginuser', 'login@example.com', 'TestPass123')
        resp = self.client.post('/auth/login/', {
            'username': 'loginuser',
            'password': 'TestPass123',
        })
        self.assertEqual(resp.status_code, 302)

    def test_login_failure(self):
        resp = self.client.post('/auth/login/', {
            'username': 'nouser',
            'password': 'wrong',
        })
        self.assertEqual(resp.status_code, 200)  # stays on page

    def test_dashboard_requires_login(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)


class ValidatorTestCase(TestCase):
    """Test validation functions."""

    def test_validate_amount_valid(self):
        from expenses.validators import validate_amount
        self.assertEqual(validate_amount('100.50'), Decimal('100.50'))
        self.assertEqual(validate_amount(42), Decimal('42.00'))

    def test_validate_amount_invalid(self):
        from expenses.validators import validate_amount
        with self.assertRaises(ValueError):
            validate_amount('0')
        with self.assertRaises(ValueError):
            validate_amount('-10')
        with self.assertRaises(ValueError):
            validate_amount('abc')

    def test_validate_date_valid(self):
        from expenses.validators import validate_date
        result = validate_date('2024-06-15')
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_validate_date_invalid(self):
        from expenses.validators import validate_date
        with self.assertRaises(ValueError):
            validate_date('not-a-date')

    def test_validate_payment_method(self):
        from expenses.validators import validate_payment_method
        self.assertEqual(validate_payment_method('UPI'), 'UPI')
        with self.assertRaises(ValueError):
            validate_payment_method('Bitcoin')

    def test_validate_category_name(self):
        from expenses.validators import validate_category_name
        self.assertEqual(validate_category_name('Food & Dining'), 'Food & Dining')
        with self.assertRaises(ValueError):
            validate_category_name('')
        with self.assertRaises(ValueError):
            validate_category_name('Bad@Name!')


class ProtectedRoutesTestCase(TestCase):
    """Ensure all routes require authentication."""

    def setUp(self):
        self.client = Client()
        self.protected_urls = [
            '/',
            '/transactions/',
            '/expenses/add/',
            '/categories/',
            '/reports/',
            '/import/',
            '/settings/',
        ]

    def test_all_protected_routes_redirect(self):
        for url in self.protected_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, f"{url} should redirect when not logged in")
            self.assertIn('/auth/login/', resp.url, f"{url} should redirect to login")
