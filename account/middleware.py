from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages


class AccountCheckMiddleWare(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user  # Who is the current user ?
        if user.is_authenticated:
            if user.user_type == '1':  # Admin
                if modulename == 'voting.views':
                    error = True
                    if request.path == reverse('fetch_ballot'):
                        pass
                    else:
                        messages.error(
                            request, "You do not have access to this resource")
                        return redirect(reverse('adminDashboard'))

            elif user.user_type == '2':  # Voter
                # or modulename == 'main_app.hod_views':
                if modulename == 'administrator.views':
                    messages.error(
                        request, "You do not have access to this resource")
                    return redirect(reverse('voterDashboard'))
            else:  # None of the aforementioned ? Please take the user to login page
                return redirect(reverse('account_login'))
        else:
            # If the path is login or has anything to do with authentication, pass
            if request.path == reverse('account_login') or modulename == 'django.contrib.auth.views' or request.path == reverse('account_login'):
                pass
            else:
                return redirect(reverse('account_login'))
