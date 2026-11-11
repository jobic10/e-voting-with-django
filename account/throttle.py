"""Small cache based rate limiting helpers (no extra dependency needed)."""
from django.core.cache import cache


def client_ip(request):
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_limited(key, limit):
    return cache.get(key, 0) >= limit


def hit(key, window):
    """Count one attempt for ``key`` and return the new total."""
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # Key expired between add() and incr()
        cache.set(key, 1, window)
        return 1


def reset(key):
    cache.delete(key)
