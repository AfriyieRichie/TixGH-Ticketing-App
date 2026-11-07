from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.core.phone import InvalidPhoneNumber


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate with an email address or a phone number plus password."""

    def authenticate(self, request, username=None, password=None, identifier=None, **kwargs):
        identifier = identifier or username or kwargs.get(get_user_model().USERNAME_FIELD)
        if not identifier or not password:
            return None
        User = get_user_model()
        try:
            user = User.objects.get_by_identifier(identifier)
        except (User.DoesNotExist, InvalidPhoneNumber):
            # Run the hasher anyway to reduce timing differences.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
