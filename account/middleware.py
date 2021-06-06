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
                    from urllib.parse import urlparse
                    url = urlparse(request.path).path
                    from django.urls import resolve
                    try:
                        redirect_url = resolve(url)
                        if redirect_url.url_name == 'fetch_ballot':
                            error = False
                            pass
                    except Exception as e:
                        pass
                    if error:
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
