from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, reverse

ADMIN = '1'
VOTER = '2'

HOME_FOR_ROLE = {
    ADMIN: 'adminDashboard',
    VOTER: 'voterDashboard',
}


def _wants_json(request):
    return (request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('accept', ''))


def role_required(role):
    """Only let authenticated users with the given ``user_type`` through."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if _wants_json(request):
                    return JsonResponse({'error': True, 'message': 'Authentication required'}, status=401)
                messages.error(request, "You need to be logged in to perform this operation")
                return redirect(reverse('account_login'))
            if str(user.user_type) != role:
                if _wants_json(request):
                    return JsonResponse({'error': True, 'message': 'Permission denied'}, status=403)
                messages.error(request, "You do not have access to this resource")
                home = HOME_FOR_ROLE.get(str(user.user_type))
                return redirect(reverse(home) if home else reverse('account_logout'))
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


admin_required = role_required(ADMIN)
voter_required = role_required(VOTER)
