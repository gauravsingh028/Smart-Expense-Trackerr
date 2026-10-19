"""
Django views for the expense tracker.

All views are login-required. Every query is scoped to request.user.id.
"""

import csv
import io
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import services
from .validators import PAYMENT_METHODS


# ─────────────────────── Helpers ───────────────────────

def _parse_date_range(request):
    """Extract start_date/end_date from GET params."""
    preset = request.GET.get('range', '')
    now = datetime.utcnow()
    start = end = None

    if preset == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif preset == '7days':
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif preset == 'this_month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif preset == 'last_month':
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_this - timedelta(seconds=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'this_year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif preset == 'custom':
        try:
            start = datetime.strptime(request.GET.get('start', ''), '%Y-%m-%d')
        except ValueError:
            start = None
        try:
            end = datetime.strptime(request.GET.get('end', ''), '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
        except ValueError:
            end = None

    return start, end, preset


def _user_id(request):
    return request.user.id


# ─────────────────────── Dashboard ───────────────────────

@login_required
def dashboard(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    start, end, preset = _parse_date_range(request)

    stats = services.get_dashboard_stats(uid, start, end)
    cat_spending = services.get_category_spending(uid, start, end)
    monthly = services.get_monthly_spending(uid)

    # Recent transactions (last 5)
    recent, _, _ = services.list_expenses(uid, per_page=5, sort_by='date', sort_dir=-1)

    color_map = services.get_category_color_map(uid)

    context = {
        'stats': stats,
        'cat_spending': cat_spending,
        'cat_spending_json': json.dumps([
            {'category': c['category'], 'total': float(c['total']), 'color': c['color']}
            for c in cat_spending
        ]),
        'monthly_json': json.dumps(monthly),
        'recent': recent,
        'color_map': color_map,
        'preset': preset,
        'payment_methods': PAYMENT_METHODS,
        'page_title': 'Dashboard',
    }
    return render(request, 'dashboard.html', context)


# ─────────────────────── Transactions (list) ───────────────────────

@login_required
def transactions(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    start, end, preset = _parse_date_range(request)

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    payment_method = request.GET.get('payment_method', '').strip()
    page = int(request.GET.get('page', 1))

    expenses, total, total_pages = services.list_expenses(
        uid,
        search=search or None,
        category=category or None,
        payment_method=payment_method or None,
        start_date=start,
        end_date=end,
        page=page,
    )

    categories = services.get_category_names(uid)
    color_map = services.get_category_color_map(uid)

    context = {
        'expenses': expenses,
        'total': total,
        'total_pages': total_pages,
        'page': page,
        'pages': range(1, total_pages + 1),
        'search': search,
        'category_filter': category,
        'payment_filter': payment_method,
        'preset': preset,
        'categories': categories,
        'color_map': color_map,
        'payment_methods': PAYMENT_METHODS,
        'start': request.GET.get('start', ''),
        'end': request.GET.get('end', ''),
        'page_title': 'All Transactions',
    }
    return render(request, 'transactions.html', context)


# ─────────────────────── Add / Edit Expense ───────────────────────

@login_required
def add_expense(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    categories = services.get_category_names(uid)

    if request.method == 'POST':
        data = {
            'amount': request.POST.get('amount', ''),
            'description': request.POST.get('description', ''),
            'category': request.POST.get('category', ''),
            'date': request.POST.get('date', ''),
            'payment_method': request.POST.get('payment_method', ''),
            'notes': request.POST.get('notes', ''),
        }
        try:
            services.create_expense(uid, data)
            messages.success(request, 'Expense added successfully!')
            return redirect('dashboard')
        except ValueError as e:
            messages.error(request, str(e))

    context = {
        'categories': categories,
        'payment_methods': PAYMENT_METHODS,
        'today': datetime.utcnow().strftime('%Y-%m-%d'),
        'page_title': 'Add Expense',
        'editing': False,
    }
    return render(request, 'expense_form.html', context)


@login_required
def edit_expense(request, expense_id):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    expense = services.get_expense(uid, expense_id)
    if not expense:
        messages.error(request, 'Expense not found.')
        return redirect('transactions')

    categories = services.get_category_names(uid)

    if request.method == 'POST':
        data = {
            'amount': request.POST.get('amount', ''),
            'description': request.POST.get('description', ''),
            'category': request.POST.get('category', ''),
            'date': request.POST.get('date', ''),
            'payment_method': request.POST.get('payment_method', ''),
            'notes': request.POST.get('notes', ''),
        }
        try:
            services.update_expense(uid, expense_id, data)
            messages.success(request, 'Expense updated successfully!')
            return redirect('transactions')
        except ValueError as e:
            messages.error(request, str(e))

    context = {
        'expense': expense,
        'categories': categories,
        'payment_methods': PAYMENT_METHODS,
        'page_title': 'Edit Expense',
        'editing': True,
    }
    return render(request, 'expense_form.html', context)


@login_required
@require_POST
def delete_expense(request, expense_id):
    uid = _user_id(request)
    try:
        services.delete_expense(uid, expense_id)
        messages.success(request, 'Expense deleted.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('transactions')


# ─────────────────────── Categories ───────────────────────

@login_required
def categories(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'add':
            try:
                services.add_category(uid, request.POST.get('name', ''), request.POST.get('color', ''))
                messages.success(request, 'Category added!')
            except ValueError as e:
                messages.error(request, str(e))
        elif action == 'edit':
            try:
                services.update_category(
                    uid,
                    request.POST.get('old_name', ''),
                    request.POST.get('name', ''),
                    request.POST.get('color', ''),
                )
                messages.success(request, 'Category updated!')
            except ValueError as e:
                messages.error(request, str(e))
        elif action == 'delete':
            try:
                services.delete_category(uid, request.POST.get('name', ''))
                messages.success(request, 'Category deleted!')
            except ValueError as e:
                messages.error(request, str(e))
        return redirect('categories')

    cats = services.get_user_categories(uid)
    # Get spending per category
    cat_spending = {c['category']: c['total'] for c in services.get_category_spending(uid)}
    for cat in cats:
        cat['spending'] = cat_spending.get(cat['name'], Decimal('0'))
        cat['spending_display'] = f"{cat['spending']:,.2f}"
        cat['id'] = str(cat['_id'])

    context = {
        'categories': cats,
        'page_title': 'Categories',
    }
    return render(request, 'categories.html', context)


# ─────────────────────── Reports ───────────────────────

@login_required
def reports(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    start, end, preset = _parse_date_range(request)

    stats = services.get_dashboard_stats(uid, start, end)
    cat_spending = services.get_category_spending(uid, start, end)
    monthly = services.get_monthly_spending(uid)

    # Daily spending for bar chart
    if start and end:
        daily = services.get_weekly_spending(uid, start, end)
    else:
        # Default to this month
        now = datetime.utcnow()
        m_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        daily = services.get_weekly_spending(uid, m_start, now)

    context = {
        'stats': stats,
        'cat_spending': cat_spending,
        'cat_spending_json': json.dumps([
            {'category': c['category'], 'total': float(c['total']), 'color': c['color']}
            for c in cat_spending
        ]),
        'monthly_json': json.dumps(monthly),
        'daily_json': json.dumps(daily),
        'preset': preset,
        'start': request.GET.get('start', ''),
        'end': request.GET.get('end', ''),
        'page_title': 'Reports & Analytics',
    }
    return render(request, 'reports.html', context)


# ─────────────────────── Bank Statement Import ───────────────────────

@login_required
def import_csv(request):
    uid = _user_id(request)
    services.ensure_default_categories(uid)
    categories = services.get_category_names(uid)

    context = {
        'page_title': 'Import Statement',
        'categories': categories,
        'preview': None,
        'errors': [],
        'filename': '',
        'file_type': '',
        'needs_password': False,
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'preview')

        if action == 'preview' or action == 'password_retry':
            # For password retry, get the file from session
            if action == 'password_retry':
                import base64
                stored = request.session.get('pdf_file_b64')
                filename = request.session.get('pdf_filename', 'statement.pdf')
                password = request.POST.get('pdf_password', '')
                if not stored:
                    messages.error(request, 'Session expired. Please upload the file again.')
                    return redirect('import_csv')
                file_bytes = base64.b64decode(stored)
            else:
                uploaded = request.FILES.get('csv_file')
                if not uploaded:
                    messages.error(request, 'Please select a file to upload.')
                    return render(request, 'import_csv.html', context)

                allowed_exts = ('.csv', '.pdf', '.xlsx', '.xls', '.txt')
                ext = uploaded.name.lower().rsplit('.', 1)[-1] if '.' in uploaded.name else ''
                if f'.{ext}' not in allowed_exts:
                    messages.error(request, f'Unsupported file type. Accepted: {", ".join(allowed_exts)}')
                    return render(request, 'import_csv.html', context)

                if uploaded.size > 10 * 1024 * 1024:
                    messages.error(request, 'File too large (max 10 MB).')
                    return render(request, 'import_csv.html', context)

                file_bytes = uploaded.read()
                filename = uploaded.name
                password = request.POST.get('pdf_password', '')

            from .bank_parser import parse_bank_statement
            valid_rows, error_rows, file_type = parse_bank_statement(
                file_bytes, filename, password=password or None
            )

            # Handle password-protected PDF
            if error_rows and len(error_rows) == 1 and error_rows[0].get('errors') == 'PDF_PASSWORD_REQUIRED':
                import base64
                # Store PDF in session temporarily (base64 to be JSON safe)
                request.session['pdf_file_b64'] = base64.b64encode(file_bytes).decode('ascii')
                request.session['pdf_filename'] = filename
                context['needs_password'] = True
                context['filename'] = filename
                context['file_type'] = 'PDF'
                return render(request, 'import_csv.html', context)

            # Clear stored PDF if not needed
            request.session.pop('pdf_file_b64', None)
            request.session.pop('pdf_filename', None)

            if not valid_rows and not error_rows:
                messages.error(request, 'No transactions found in the file. Check the format.')
                return render(request, 'import_csv.html', context)

            if not valid_rows and error_rows:
                if len(error_rows) == 1 and error_rows[0].get('row', 0) in (0, 1):
                    messages.error(request, error_rows[0]['errors'])
                    return render(request, 'import_csv.html', context)

            # Store in session for confirmation
            request.session['csv_rows'] = valid_rows
            request.session['csv_errors'] = error_rows
            context['preview'] = valid_rows[:100]
            context['errors'] = error_rows
            context['valid_count'] = len(valid_rows)
            context['error_count'] = len(error_rows)
            context['filename'] = filename
            context['file_type'] = file_type

        elif action == 'import':
            rows = request.session.pop('csv_rows', [])
            request.session.pop('csv_errors', None)
            if not rows:
                messages.error(request, 'No data to import. Please upload again.')
                return redirect('import_csv')
            imported, skipped = services.import_csv_rows(uid, rows)
            messages.success(request, f'Imported {imported} transaction(s). {skipped} duplicate(s) skipped.')
            return redirect('transactions')

    return render(request, 'import_csv.html', context)


# ─────────────────────── Settings ───────────────────────

@login_required
def settings_page(request):
    context = {
        'page_title': 'Settings',
    }
    return render(request, 'settings.html', context)


# ─────────────────────── API endpoints (for chart refresh) ─────

@login_required
def api_dashboard_data(request):
    """Return JSON dashboard data for AJAX chart updates."""
    uid = _user_id(request)
    start, end, _ = _parse_date_range(request)

    stats = services.get_dashboard_stats(uid, start, end)
    cat_spending = services.get_category_spending(uid, start, end)
    monthly = services.get_monthly_spending(uid)

    return JsonResponse({
        'stats': {
            'total_expenses': str(stats['total_expenses']),
            'month_expenses': str(stats['month_expenses']),
            'avg_daily': str(stats['avg_daily']),
            'top_category': stats['top_category'],
            'top_category_amount': str(stats['top_category_amount']),
            'month_change_pct': str(stats['month_change_pct']) if stats['month_change_pct'] is not None else None,
        },
        'cat_spending': [
            {'category': c['category'], 'total': float(c['total']), 'color': c['color']}
            for c in cat_spending
        ],
        'monthly': monthly,
    })
