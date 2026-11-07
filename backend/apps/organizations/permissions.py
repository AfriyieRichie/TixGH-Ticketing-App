from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Organization


class OrgScopedMixin:
    """
    For views nested under /organizations/<org_slug>/...

    Set `required_perm` (a Perm constant) on the view, or override
    `get_required_perm()` to vary it by HTTP method.
    """

    required_perm: str | None = None

    def get_required_perm(self) -> str | None:
        return self.required_perm

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.organization = get_object_or_404(
            Organization, slug=kwargs["org_slug"], is_active=True
        )
        self.membership = self.organization.membership_for(request.user)
        if self.membership is None:
            raise Http404  # Don't reveal organizations the user isn't part of.
        perm = self.get_required_perm()
        if perm and not self.membership.can(perm):
            raise PermissionDenied("Your team role does not allow this action.")
