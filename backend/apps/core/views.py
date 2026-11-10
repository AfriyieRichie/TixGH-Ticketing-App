import hmac
import logging

from django.conf import settings
from django.http import Http404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer

from apps.growth.services import process_campaigns, send_review_requests
from apps.payments.refunds import check_refunds
from apps.notifications.services import send_due_reminders
from apps.orders.services import expire_stale_orders

from .constants import GhanaRegion, MobileMoneyProvider
from .models import PlatformSettings

logger = logging.getLogger(__name__)


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


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([AllowAny])
def cron(request):
    """
    Periodic jobs for hosts without a background worker. Call every ~10 minutes
    (e.g. from cron-job.org) with header  X-Cron-Secret: <CRON_SECRET>.
    Also keeps a free server from going to sleep.
    """
    secret = settings.CRON_SECRET
    given = request.headers.get("X-Cron-Secret", "")
    if not secret or not hmac.compare_digest(given, secret):
        raise Http404
    result = {
        "expired_orders": expire_stale_orders(),
        "reminders_sent": send_due_reminders(),
        "campaign_emails": process_campaigns(),
        "review_requests": send_review_requests(),
        "refunds": check_refunds(),
    }
    logger.info("cron: %s", result)
    return Response(result)
