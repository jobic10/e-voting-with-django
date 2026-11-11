from django.test import override_settings
from django.urls import reverse

from account.models import CustomUser
from voting.models import Voter
from voting.testing import PASSWORD, BaseTestCase, make_admin, make_voter


class LoginTests(BaseTestCase):
    def test_admin_login_redirects_to_admin_dashboard(self):
        make_admin()
        response = self.client.post(reverse('account_login'), {
            'email': 'admin@example.com', 'password': PASSWORD})
        self.assertRedirects(response, reverse('adminDashboard'), fetch_redirect_response=False)

    def test_voter_login_is_case_insensitive(self):
        make_voter()
        response = self.client.post(reverse('account_login'), {
            'email': 'VOTER@example.com', 'password': PASSWORD})
        self.assertRedirects(response, reverse('voterDashboard'), fetch_redirect_response=False)

    def test_wrong_password_rejected(self):
        make_voter()
        self.client.post(reverse('account_login'), {
            'email': 'voter@example.com', 'password': 'nope'})
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(LOGIN_MAX_ATTEMPTS=3)
    def test_login_locked_after_repeated_failures(self):
        make_voter()
        for _ in range(3):
            self.client.post(reverse('account_login'), {
                'email': 'voter@example.com', 'password': 'wrong'})
        # Even the right password is refused while locked out
        self.client.post(reverse('account_login'), {
            'email': 'voter@example.com', 'password': PASSWORD})
        self.assertNotIn('_auth_user_id', self.client.session)


class RegistrationTests(BaseTestCase):
    def data(self, **overrides):
        data = {
            'first_name': 'New', 'last_name': 'Voter', 'email': 'new@example.com',
            'password': PASSWORD, 'phone': '08011111111',
        }
        data.update(overrides)
        return data

    def test_registration_creates_voter(self):
        response = self.client.post(reverse('account_register'), self.data())
        self.assertRedirects(response, reverse('account_login'), fetch_redirect_response=False)
        user = CustomUser.objects.get(email='new@example.com')
        self.assertEqual(user.user_type, '2')
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(Voter.objects.filter(admin=user).exists())

    def test_registration_cannot_create_admin(self):
        self.client.post(reverse('account_register'), self.data(user_type='1'))
        self.assertEqual(CustomUser.objects.get(email='new@example.com').user_type, '2')

    def test_weak_password_rejected(self):
        self.client.post(reverse('account_register'), self.data(password='123'))
        self.assertFalse(CustomUser.objects.filter(email='new@example.com').exists())

    def test_duplicate_email_rejected_case_insensitively(self):
        make_voter(email='new@example.com')
        self.client.post(reverse('account_register'), self.data(
            email='NEW@example.com', phone='08022222222'))
        self.assertEqual(CustomUser.objects.filter(email__iexact='new@example.com').count(), 1)

    @override_settings(ALLOW_VOTER_REGISTRATION=False)
    def test_registration_can_be_closed(self):
        self.client.post(reverse('account_register'), self.data())
        self.assertFalse(CustomUser.objects.filter(email='new@example.com').exists())

    @override_settings(REGISTRATION_MAX_PER_IP=1)
    def test_registration_rate_limited_per_ip(self):
        self.client.post(reverse('account_register'), self.data())
        self.client.post(reverse('account_register'), self.data(
            email='second@example.com', phone='08033333333'))
        self.assertFalse(CustomUser.objects.filter(email='second@example.com').exists())


class AccessControlTests(BaseTestCase):
    def test_anonymous_users_are_sent_to_login(self):
        for name in ('adminDashboard', 'viewVotes', 'voterDashboard', 'show_ballot'):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse('account_login'),
                                 fetch_redirect_response=False, msg_prefix=name)

    def test_unknown_role_is_logged_out(self):
        user = make_voter()
        CustomUser.objects.filter(pk=user.pk).update(user_type='9')
        self.client.force_login(user)
        response = self.client.get(reverse('voterDashboard'))
        self.assertRedirects(response, reverse('account_login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)


class LogoutTests(BaseTestCase):
    def test_logout_requires_post(self):
        user = make_voter()
        self.client.force_login(user)
        response = self.client.get(reverse('account_logout'))
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_requires_csrf_token(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(make_voter())
        response = client.post(reverse('account_logout'))
        self.assertEqual(response.status_code, 403)
        self.assertIn('_auth_user_id', client.session)

    def test_post_logs_out(self):
        self.client.force_login(make_voter())
        response = self.client.post(reverse('account_logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_rendered_as_form(self):
        self.client.force_login(make_admin())
        content = self.client.get(reverse('adminDashboard')).content.decode()
        self.assertIn('action="%s"' % reverse('account_logout'), content)
        self.assertNotIn('href="%s"' % reverse('account_logout'), content)
