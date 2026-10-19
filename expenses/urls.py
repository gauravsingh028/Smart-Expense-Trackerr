"""URL patterns for the expenses app (main routes)."""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions, name='transactions'),
    path('expenses/add/', views.add_expense, name='add_expense'),
    path('expenses/<str:expense_id>/edit/', views.edit_expense, name='edit_expense'),
    path('expenses/<str:expense_id>/delete/', views.delete_expense, name='delete_expense'),
    path('categories/', views.categories, name='categories'),
    path('reports/', views.reports, name='reports'),
    path('import/', views.import_csv, name='import_csv'),
    path('settings/', views.settings_page, name='settings'),
    path('api/dashboard/', views.api_dashboard_data, name='api_dashboard'),
]
