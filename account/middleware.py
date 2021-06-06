from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse
from django.shortcuts import redirect


class AccountCheckMiddleWare(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user  # Who is the current user ?
        if user.is_authenticated:
            if user.user_type == '1':  # Admin
                if modulename == 'main_app.student_views':
                    return redirect(reverse('admin_home'))
            elif user.user_type == '2':  # Voter
                if modulename == 'main_app.student_views' or modulename == 'main_app.hod_views':
                    return redirect(reverse('staff_home'))
            else:  # None of the aforementioned ? Please take the user to login page
                return redirect(reverse('account_login'))
        else:
            # If the path is login or has anything to do with authentication, pass
            if request.path == reverse('account_login') or modulename == 'django.contrib.auth.views' or request.path == reverse('account_login'):
                pass
            else:
                return redirect(reverse('account_login'))
