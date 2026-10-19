"""Root URL configuration."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('expenses.auth_urls')),
    path('', include('expenses.urls')),
]
