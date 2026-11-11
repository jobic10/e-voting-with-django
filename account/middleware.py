from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

# Paths anonymous users may reach.
PUBLIC_URL_NAMES = ('account_login', 'account_register')


class AccountCheckMiddleWare(MiddlewareMixin):
    """Coarse access control. Every view is also protected by
    ``account.decorators.admin_required`` / ``voter_required``."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user  # Who is the current user ?
        if user.is_authenticated:
            if user.user_type == '1':  # Admin
                if modulename == 'voting.views' and request.path != reverse('fetch_ballot'):
                    messages.error(
                        request, "You do not have access to this resource")
                    return redirect(reverse('adminDashboard'))
            elif user.user_type == '2':  # Voter
                if modulename == 'administrator.views' or request.path == reverse('fetch_ballot'):
                    messages.error(
                        request, "You do not have access to this resource")
                    return redirect(reverse('voterDashboard'))
            else:  # Unknown role: end the session instead of looping on login
                logout(request)
                return redirect(reverse('account_login'))
        else:
            public_paths = [reverse(name) for name in PUBLIC_URL_NAMES]
            if request.path in public_paths or modulename == 'django.contrib.auth.views':
                return None
            if modulename in ('administrator.views', 'voting.views'):
                messages.error(
                    request, "You need to be logged in to perform this operation")
            return redirect(reverse('account_login'))
