"""Root URL configuration."""

from django.urls import path, include

urlpatterns = [
    path('auth/', include('expenses.auth_urls')),
    path('', include('expenses.urls')),
]
