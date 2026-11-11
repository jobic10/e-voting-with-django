from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.shortcuts import redirect, render, reverse

from voting.forms import VoterForm

from . import throttle
from .forms import CustomUserForm


def _home_for(user):
    if user.user_type == '1':
        return reverse("adminDashboard")
    return reverse("voterDashboard")


def account_login(request):
    if request.user.is_authenticated:
        return redirect(_home_for(request.user))

    context = {}
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        password = request.POST.get('password')
        key = "login-fail:%s:%s" % (throttle.client_ip(request), email)
        if throttle.is_limited(key, settings.LOGIN_MAX_ATTEMPTS):
            messages.error(request, "Too many failed login attempts. Please try again later.")
            return redirect(reverse('account_login'))
        user = authenticate(request, username=email, password=password)
        if user is not None:
            throttle.reset(key)
            login(request, user)
            return redirect(_home_for(user))
        throttle.hit(key, settings.LOGIN_LOCKOUT_SECONDS)
        messages.error(request, "Invalid details")
        return redirect(reverse('account_login'))

    return render(request, "voting/login.html", context)


def account_register(request):
    if not settings.ALLOW_VOTER_REGISTRATION:
        messages.error(request, "Voter registration is closed")
        return redirect(reverse('account_login'))
    userForm = CustomUserForm(request.POST or None)
    voterForm = VoterForm(request.POST or None)
    context = {
        'form1': userForm,
        'form2': voterForm
    }
    if request.method == 'POST':
        key = "register:%s" % throttle.client_ip(request)
        if throttle.is_limited(key, settings.REGISTRATION_MAX_PER_IP):
            messages.error(request, "Too many registrations from your network. Please try again later.")
            return redirect(reverse('account_register'))
        if userForm.is_valid() and voterForm.is_valid():
            with transaction.atomic():
                user = userForm.save(commit=False)
                user.user_type = '2'  # Self registration can only create voters
                voter = voterForm.save(commit=False)
                user.save()
                voter.admin = user
                voter.save()
            throttle.hit(key, settings.REGISTRATION_WINDOW_SECONDS)
            messages.success(request, "Account created. You can login now!")
            return redirect(reverse('account_login'))
        else:
            messages.error(request, "Provided data failed validation")
    return render(request, "voting/reg.html", context)


def account_logout(request):
    user = request.user
    if user.is_authenticated:
        logout(request)
        messages.success(request, "Thank you for visiting us!")
    else:
        messages.error(
            request, "You need to be logged in to perform this action")

    return redirect(reverse("account_login"))
