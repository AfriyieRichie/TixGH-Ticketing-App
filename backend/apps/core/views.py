from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer

from .constants import GhanaRegion, MobileMoneyProvider
from .models import PlatformSettings


@extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


@extend_schema(responses=inline_serializer("PublicConfig", {"platform_name": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def public_config(request):
    """Settings the web and mobile apps need at startup."""
    ps = PlatformSettings.load()
    return Response(
        {
            "platform_name": settings.PLATFORM_NAME,
            "currency": ps.currency,
            "fees": {
                "percent": str(ps.fee_percent),
                "flat": str(ps.fee_flat),
                "cap": str(ps.fee_cap) if ps.fee_cap is not None else None,
                "default_bearer": ps.default_fee_bearer,
            },
            "support": {"email": ps.support_email, "phone": ps.support_phone},
            "regions": [{"value": v, "label": l} for v, l in GhanaRegion.choices],
            "mobile_money_providers": [
                {"value": v, "label": l} for v, l in MobileMoneyProvider.choices
            ],
        }
    )
