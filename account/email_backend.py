from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None
        try:
            user = UserModel.objects.get(email__iexact=username.strip())
        except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
            # Run the hasher anyway to reduce timing differences between
            # existing and non-existing accounts.
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
