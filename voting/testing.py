"""Shared fixtures for the test suites."""
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from account.models import CustomUser

from .models import Candidate, Position, Voter

PASSWORD = 'Sup3r-Secret-Passw0rd!'


def make_admin(email='admin@example.com'):
    return CustomUser.objects.create_user(
        email=email, password=PASSWORD, user_type='1',
        first_name='Admin', last_name='User', is_staff=True)


def make_voter(email='voter@example.com', phone='08000000001', verified=True, voted=False):
    user = CustomUser.objects.create_user(
        email=email, password=PASSWORD, user_type='2',
        first_name='Vote', last_name='Er')
    Voter.objects.create(
        admin=user, phone=phone, verified=verified, voted=voted,
        otp='123456' if verified else None)
    return user


def make_position(name, max_vote=1, priority=None):
    if priority is None:
        priority = Position.objects.count() + 1
    return Position.objects.create(name=name, max_vote=max_vote, priority=priority)


def make_candidate(position, fullname='Candidate', bio='Bio'):
    return Candidate.objects.create(
        fullname=fullname, bio=bio, position=position, photo='candidates/x.jpg')


class BaseTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # Rate limiting counters live in the cache

    def count_queries(self, func):
        with CaptureQueriesContext(connection) as ctx:
            func()
        return len(ctx.captured_queries)
