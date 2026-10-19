"""Authentication views: register, login, logout."""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        errors = []
        if not username:
            errors.append('Username is required.')
        if not email:
            errors.append('Email is required.')
        if not password1:
            errors.append('Password is required.')
        if password1 != password2:
            errors.append('Passwords do not match.')
        if len(password1) < 8:
            errors.append('Password must be at least 8 characters.')
        if User.objects.filter(username=username).exists():
            errors.append('Username already taken.')
        if User.objects.filter(email=email).exists():
            errors.append('Email already registered.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                first_name=first_name,
                last_name=last_name,
            )
            login(request, user)
            messages.success(request, f'Welcome, {first_name or username}!')
            return redirect('dashboard')

    return render(request, 'registration/register.html', {'page_title': 'Create Account'})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'registration/login.html', {'page_title': 'Sign In'})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')
