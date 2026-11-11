import json
import os
import tempfile
import unittest

from django.test import Client, override_settings
from django.urls import reverse

from voting.models import Candidate, Position, Voter, Votes
from voting.testing import (BaseTestCase, make_admin, make_candidate,
                            make_position, make_voter)

from .views import find_n_winners, get_result_context

XSS = '<script>alert("x")</script>'

try:
    import weasyprint  # noqa: F401
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    HAS_WEASYPRINT = False


def cast_vote(voter_user, candidate):
    voter = Voter.objects.get(admin=voter_user)
    Votes.objects.create(voter=voter, candidate=candidate, position=candidate.position)
    Voter.objects.filter(pk=voter.pk).update(voted=True)


class AdminAccessTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()
        self.voter = make_voter()
        position = make_position('President')
        self.candidate = make_candidate(position, 'Ada')
        cast_vote(self.voter, self.candidate)

    def test_voter_cannot_access_admin_pages(self):
        self.client.force_login(self.voter)
        for name in ('adminDashboard', 'viewVotes', 'adminViewVoters', 'viewCandidates'):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse('voterDashboard'),
                                 fetch_redirect_response=False, msg_prefix=name)

    def test_voter_cannot_reset_votes(self):
        self.client.force_login(self.voter)
        self.client.post(reverse('resetVote'))
        self.assertEqual(Votes.objects.count(), 1)

    def test_reset_votes_rejects_get(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('resetVote'))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Votes.objects.count(), 1)

    def test_reset_votes_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('resetVote'))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Votes.objects.count(), 1)

    def test_reset_votes_with_post(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('resetVote'))
        self.assertRedirects(response, reverse('viewVotes'), fetch_redirect_response=False)
        self.assertEqual(Votes.objects.count(), 0)
        self.assertFalse(Voter.objects.get(admin=self.voter).voted)

    def test_votes_page_has_post_reset_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('viewVotes'))
        self.assertContains(response, 'action="%s"' % reverse('resetVote'))
        self.assertNotContains(response, 'href="%s"' % reverse('resetVote'))

    def test_destructive_endpoints_reject_get(self):
        self.client.force_login(self.admin)
        for name in ('deleteVoter', 'deletePosition', 'deleteCandidate',
                     'updateVoter', 'updatePosition', 'updateCandidate', 'ballot_title'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 405, name)
        url = reverse('update_ballot_position', args=[self.candidate.position.id, 'up'])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_delete_candidate_with_post(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('deleteCandidate'), {'id': self.candidate.id})
        self.assertFalse(Candidate.objects.exists())


class BallotPositionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_admin())
        self.a = make_position('A')
        self.b = make_position('B')

    def move(self, position, direction):
        url = reverse('update_ballot_position', args=[position.id, direction])
        return json.loads(self.client.post(url).content)

    def test_move_down_and_up(self):
        self.assertFalse(self.move(self.a, 'down')['error'])
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.a.priority, self.b.priority), (2, 1))
        self.assertTrue(self.move(self.b, 'up')['error'])  # Already at the top

    def test_invalid_direction(self):
        url = reverse('update_ballot_position', args=[self.a.id, 'sideways'])
        self.assertEqual(self.client.post(url).status_code, 400)


class ElectionTitleTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_admin())
        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.addCleanup(os.remove, self.path)

    def test_title_is_saved_and_escaped(self):
        with override_settings(ELECTION_TITLE_PATH=self.path):
            self.client.post(reverse('ballot_title'), {'title': XSS},
                             HTTP_REFERER='http://evil.example.com/')
            with open(self.path) as f:
                self.assertEqual(f.read(), XSS)
            response = self.client.get(reverse('adminDashboard'))
        self.assertNotContains(response, XSS)
        self.assertContains(response, '&lt;script&gt;')

    def test_title_redirect_ignores_foreign_referer(self):
        with override_settings(ELECTION_TITLE_PATH=self.path):
            response = self.client.post(reverse('ballot_title'), {'title': 'Ok'},
                                        HTTP_REFERER='http://evil.example.com/')
        self.assertRedirects(response, reverse('adminDashboard'), fetch_redirect_response=False)

    def test_title_length_is_limited(self):
        with override_settings(ELECTION_TITLE_PATH=self.path):
            self.client.post(reverse('ballot_title'), {'title': 'x' * 1000})
            with open(self.path) as f:
                self.assertEqual(f.read(), '')


class PositionFormTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_admin())

    def test_max_vote_must_be_positive(self):
        self.client.post(reverse('viewPositions'), {'name': 'President', 'max_vote': 0})
        self.assertFalse(Position.objects.exists())

    def test_slug_collisions_rejected(self):
        make_position('Vice President')
        self.client.post(reverse('viewPositions'), {'name': 'vice-president', 'max_vote': 1})
        self.assertEqual(Position.objects.count(), 1)


class DashboardTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def populate(self, n):
        for _ in range(n):
            index = Position.objects.count()
            position = make_position('Position %d' % index)
            for j in range(3):
                candidate = make_candidate(position, 'Candidate %d-%d' % (index, j))
                user = make_voter(email='v%d-%d@example.com' % (index, j),
                                  phone='0807%03d%04d' % (index, j))
                cast_vote(user, candidate)

    def assert_constant_queries(self, url_name):
        self.populate(1)
        small = self.count_queries(lambda: self.client.get(reverse(url_name)))
        self.populate(4)
        large = self.count_queries(lambda: self.client.get(reverse(url_name)))
        self.assertEqual(small, large, url_name)

    def test_dashboard_queries_constant(self):
        self.assert_constant_queries('adminDashboard')

    def test_votes_page_queries_constant(self):
        self.assert_constant_queries('viewVotes')

    def test_voters_page_queries_constant(self):
        self.assert_constant_queries('adminViewVoters')

    def test_candidates_page_queries_constant(self):
        self.assert_constant_queries('viewCandidates')

    def test_dashboard_vote_counts(self):
        position = make_position('President')
        ada = make_candidate(position, 'Ada')
        make_candidate(position, 'Bola')
        cast_vote(make_voter(), ada)
        response = self.client.get(reverse('adminDashboard'))
        chart = response.context['chart_data'][position]
        self.assertEqual(json.loads(chart['candidates']), ['Ada', 'Bola'])
        self.assertEqual(json.loads(chart['votes']), [1, 0])

    def test_dashboard_chart_data_is_script_safe(self):
        position = make_position('President')
        make_candidate(position, '</script><script>alert(1)</script>')
        response = self.client.get(reverse('adminDashboard'))
        self.assertNotContains(response, '</script><script>alert(1)')
        self.assertContains(response, '\\u003C/script\\u003E')


class ResultTests(BaseTestCase):
    def test_find_n_winners_orders_and_escapes(self):
        result = find_n_winners([
            {'name': 'Low', 'votes': 1},
            {'name': XSS, 'votes': 5},
            {'name': 'Mid', 'votes': 3},
        ], 2)
        self.assertTrue(result.startswith('&lt;script&gt;'))
        self.assertIn('Mid with 3 votes', result)
        self.assertNotIn('Low', result)

    def test_single_winner_is_escaped(self):
        position = make_position('President')
        winner = make_candidate(position, XSS)
        make_candidate(position, 'Other')
        cast_vote(make_voter(), winner)
        data = get_result_context()['President']
        self.assertEqual(data['winner'], 'Winner : &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')

    def test_result_context_query_count(self):
        position = make_position('President')
        make_candidate(position, 'Ada')
        self.assertEqual(self.count_queries(get_result_context), 2)

    @unittest.skipUnless(HAS_WEASYPRINT, "WeasyPrint system libraries are not installed")
    def test_print_view_returns_pdf(self):
        self.client.force_login(make_admin())
        response = self.client.get(reverse('printResult'))
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
