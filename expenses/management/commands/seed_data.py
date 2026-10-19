"""
Management command to seed demo data into MongoDB.

Usage: python manage.py seed_data
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from bson.decimal128 import Decimal128
from expenses.services import ensure_default_categories, get_category_names
from expenses.db import get_expenses_collection


class Command(BaseCommand):
    help = 'Seed demo expense data for a user.'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='demo',
                            help='Username to create/use (default: demo)')
        parser.add_argument('--count', type=int, default=60,
                            help='Number of expenses to create (default: 60)')

    def handle(self, *args, **options):
        username = options['username']
        count = options['count']

        # Get or create user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@example.com',
                'first_name': username.capitalize(),
            }
        )
        if created:
            user.set_password('demo1234')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created user: {username} / demo1234'))
        else:
            self.stdout.write(f'Using existing user: {username}')

        uid = user.id
        ensure_default_categories(uid)
        categories = get_category_names(uid)
        col = get_expenses_collection()

        payment_methods = ['Cash', 'Credit Card', 'Debit Card', 'UPI', 'Net Banking', 'Wallet']

        descriptions = {
            'Food & Dining': ['Swiggy order', 'Zomato dinner', 'Restaurant lunch', 'Coffee shop',
                              'Grocery shopping', 'BigBasket delivery', 'Street food', 'Cafe visit'],
            'Transportation': ['Uber ride', 'Ola cab', 'Metro recharge', 'Bus pass', 'Petrol fill',
                               'Rapido auto', 'Train ticket'],
            'Shopping': ['Amazon purchase', 'Flipkart order', 'Clothing store', 'Electronics store',
                         'Myntra order', 'Gift purchase'],
            'Bills & Utilities': ['Electricity bill', 'Water bill', 'Internet bill', 'Mobile recharge',
                                  'Gas cylinder', 'Rent payment'],
            'Healthcare': ['Pharmacy', 'Doctor visit', 'Lab tests', 'Medical insurance',
                           'Dental checkup'],
            'Entertainment': ['Netflix subscription', 'Movie tickets', 'Spotify premium',
                              'Concert tickets', 'Gaming purchase'],
            'Education': ['Online course', 'Book purchase', 'Udemy course', 'Stationery',
                          'Exam fees'],
            'Travel': ['Hotel booking', 'Flight ticket', 'Train booking', 'Travel insurance',
                       'Sightseeing'],
            'Other': ['Miscellaneous', 'Charity donation', 'ATM withdrawal', 'Service charge'],
        }

        amount_ranges = {
            'Food & Dining': (100, 2500),
            'Transportation': (50, 1500),
            'Shopping': (200, 8000),
            'Bills & Utilities': (300, 5000),
            'Healthcare': (100, 3000),
            'Entertainment': (100, 2000),
            'Education': (200, 5000),
            'Travel': (500, 15000),
            'Other': (50, 2000),
        }

        now = datetime.utcnow()
        inserted = 0

        for _ in range(count):
            cat = random.choice(categories)
            desc_list = descriptions.get(cat, descriptions['Other'])
            desc = random.choice(desc_list)
            lo, hi = amount_ranges.get(cat, (50, 2000))
            amount = Decimal(str(random.randint(lo * 100, hi * 100) / 100)).quantize(Decimal('0.01'))
            days_ago = random.randint(0, 365)
            date = now - timedelta(days=days_ago)
            pm = random.choice(payment_methods)

            col.insert_one({
                'user_id': uid,
                'amount': Decimal128(str(amount)),
                'description': desc,
                'category': cat,
                'date': date,
                'payment_method': pm,
                'notes': '',
                'created_at': now,
                'updated_at': now,
            })
            inserted += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {inserted} expenses for user "{username}".'))
        self.stdout.write(f'Login with: {username} / demo1234')
