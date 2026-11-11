import json

from django.test import override_settings
from django.urls import reverse

from .models import Position, Voter, Votes
from .testing import (BaseTestCase, make_admin, make_candidate, make_position,
                      make_voter)
from .views import OTP_LENGTH, generate_ballot, generate_otp

XSS = '<script>alert("x")</script>'


class OtpTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_voter(verified=False)
        Voter.objects.filter(admin=self.user).update(otp='654321')
        self.client.force_login(self.user)

    def test_generate_otp_is_numeric_and_fixed_length(self):
        otps = {generate_otp() for _ in range(50)}
        self.assertTrue(all(len(o) == OTP_LENGTH and o.isdigit() for o in otps))
        self.assertGreater(len(otps), 1)

    def test_correct_otp_verifies(self):
        response = self.client.post(reverse('verify_otp'), {'otp': '654321'})
        self.assertRedirects(response, reverse('show_ballot'), fetch_redirect_response=False)
        self.assertTrue(Voter.objects.get(admin=self.user).verified)

    def test_verify_otp_requires_post(self):
        self.assertEqual(self.client.get(reverse('verify_otp')).status_code, 405)

    @override_settings(OTP_MAX_ATTEMPTS=3)
    def test_otp_brute_force_is_locked_out(self):
        for guess in ('000000', '111111', '222222'):
            self.client.post(reverse('verify_otp'), {'otp': guess})
        self.client.post(reverse('verify_otp'), {'otp': '654321'})
        self.assertFalse(Voter.objects.get(admin=self.user).verified)

    def test_resend_otp_requires_post(self):
        self.assertEqual(self.client.get(reverse('resend_otp')).status_code, 405)

    @override_settings(SEND_OTP=False)
    def test_otp_bypass_only_verifies_current_voter(self):
        other = make_voter(email='other@example.com', phone='08099999999', verified=False)
        response = self.client.post(reverse('resend_otp'))
        self.assertFalse(json.loads(response.content)['error'])
        self.assertTrue(Voter.objects.get(admin=self.user).verified)
        self.assertFalse(Voter.objects.get(admin=other).verified)


class VotingFlowTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.president = make_position('President', max_vote=1)
        self.senate = make_position('Senate', max_vote=2)
        self.p1 = make_candidate(self.president, 'Ada')
        self.p2 = make_candidate(self.president, 'Bola')
        self.s1 = make_candidate(self.senate, 'Chi')
        self.s2 = make_candidate(self.senate, 'Dayo')
        self.s3 = make_candidate(self.senate, 'Efe')
        self.user = make_voter()
        self.client.force_login(self.user)

    def ballot(self, **extra):
        data = {'president': str(self.p1.id), 'senate[]': [str(self.s1.id), str(self.s2.id)]}
        data.update(extra)
        return data

    def test_voter_can_vote_once(self):
        response = self.client.post(reverse('submit_ballot'), self.ballot())
        self.assertRedirects(response, reverse('voterDashboard'), fetch_redirect_response=False)
        self.assertEqual(Votes.objects.count(), 3)
        self.assertTrue(Voter.objects.get(admin=self.user).voted)

        self.client.post(reverse('submit_ballot'), self.ballot())
        self.assertEqual(Votes.objects.count(), 3)

    def test_unverified_voter_cannot_vote(self):
        Voter.objects.filter(admin=self.user).update(verified=False, otp=None)
        response = self.client.post(reverse('submit_ballot'), self.ballot())
        self.assertRedirects(response, reverse('voterVerify'), fetch_redirect_response=False)
        self.assertEqual(Votes.objects.count(), 0)
        response = self.client.get(reverse('show_ballot'))
        self.assertRedirects(response, reverse('voterVerify'), fetch_redirect_response=False)

    def test_too_many_choices_rejected(self):
        self.client.post(reverse('submit_ballot'), self.ballot(
            **{'senate[]': [str(self.s1.id), str(self.s2.id), str(self.s3.id)]}))
        self.assertEqual(Votes.objects.count(), 0)

    def test_duplicate_choice_rejected(self):
        self.client.post(reverse('submit_ballot'), self.ballot(
            **{'senate[]': [str(self.s1.id), str(self.s1.id)]}))
        self.assertEqual(Votes.objects.count(), 0)

    def test_candidate_from_other_position_rejected(self):
        self.client.post(reverse('submit_ballot'), self.ballot(president=str(self.s1.id)))
        self.assertEqual(Votes.objects.count(), 0)
        self.assertFalse(Voter.objects.get(admin=self.user).voted)

    def test_ballot_page_renders_for_verified_voter(self):
        response = self.client.get(reverse('show_ballot'))
        self.assertContains(response, 'name="president"')
        self.assertContains(response, 'name="senate[]"')
        self.assertContains(response, "X-CSRFToken")

    def test_verify_page_renders(self):
        response = self.client.get(reverse('voterVerify'))
        self.assertContains(response, reverse('resend_otp'))

    def test_submit_requires_post(self):
        self.assertEqual(self.client.get(reverse('submit_ballot')).status_code, 405)

    def test_preview_lists_choices_escaped(self):
        make_candidate(self.president, XSS)
        xss_id = self.president.candidate_set.get(fullname=XSS).id
        response = self.client.post(reverse('preview_vote'), self.ballot(president=str(xss_id)))
        data = json.loads(response.content)
        self.assertFalse(data['error'])
        self.assertNotIn('<script>', data['list'])
        self.assertIn('&lt;script&gt;', data['list'])

    def test_preview_reports_errors(self):
        response = self.client.post(reverse('preview_vote'), self.ballot(president='999999'))
        self.assertTrue(json.loads(response.content)['error'])

    def test_voted_dashboard_shows_my_votes(self):
        self.client.post(reverse('submit_ballot'), self.ballot())
        response = self.client.get(reverse('voterDashboard'))
        self.assertContains(response, 'Ada')

    def test_admin_cannot_use_voter_views(self):
        self.client.force_login(make_admin())
        response = self.client.get(reverse('show_ballot'))
        self.assertRedirects(response, reverse('adminDashboard'), fetch_redirect_response=False)

    def test_voter_cannot_fetch_admin_ballot(self):
        response = self.client.get(reverse('fetch_ballot'))
        self.assertNotEqual(response.status_code, 200)


class BallotRenderingTests(BaseTestCase):
    def test_ballot_escapes_user_content(self):
        position = make_position(XSS)
        make_candidate(position, fullname=XSS, bio='"><img src=x onerror=alert(1)>')
        html = generate_ballot(display_controls=True)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;', html)

    def test_ballot_query_count_does_not_grow_with_data(self):
        def build(n):
            for i in range(n):
                position = make_position('Position %d' % Position.objects.count())
                for j in range(3):
                    make_candidate(position, 'Candidate %d' % j)
            return self.count_queries(generate_ballot)

        small = build(1)
        large = build(5)
        self.assertEqual(small, large)
        self.assertLessEqual(large, 2)

    def test_ballot_renumbers_priorities_once(self):
        make_position('A', priority=5)
        make_position('B', priority=9)
        generate_ballot()
        self.assertEqual(list(Position.objects.order_by('priority').values_list('priority', flat=True)), [1, 2])
        # Already contiguous: rendering again must not write anything
        self.assertEqual(self.count_queries(generate_ballot), 2)
