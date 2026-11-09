"""
Organizer marketing: audiences, campaigns, unsubscribes, follower alerts and
post-event review requests.

Email goes through the normal EMAIL_BACKEND (Brevo in production). Free email
plans have a daily cap, so campaigns are queued and drained in batches by the
scheduled job (`process_campaigns`), never more than CAMPAIGN_DAILY_LIMIT a day;
whatever is left continues the next day.
"""

import logging
from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Avg, Count, F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.events.models import Event, EventStatus
from apps.orders.models import Order, OrderStatus
from apps.tickets.rendering import format_when, format_where

from .models import (
    Campaign, CampaignAudience, CampaignRecipient, CampaignStatus, Follow, RecipientStatus, Unsubscribe,
)

logger = logging.getLogger(__name__)
UNSUB_SALT = "growth.unsubscribe"


class CampaignError(Exception):
    pass


def rating_summary(reviews_qs) -> dict:
    agg = reviews_qs.filter(is_hidden=False).aggregate(avg=Avg("rating"), n=Count("id"))
    return {"average": round(agg["avg"], 1) if agg["avg"] else None, "count": agg["n"]}


# --------------------------------------------------------------------------
# Audience
# --------------------------------------------------------------------------
def audience_contacts(org, audience: str = CampaignAudience.ALL) -> dict[str, str]:
    """{email: name} for people who agreed to hear from this organizer, minus unsubscribes."""
    contacts: dict[str, str] = {}
    if audience in (CampaignAudience.ALL, CampaignAudience.FOLLOWERS):
        for email, name in Follow.objects.filter(organization=org, user__is_active=True, user__email__isnull=False) \
                .values_list("user__email", "user__full_name"):
            contacts.setdefault(email.lower(), name or "")
    if audience in (CampaignAudience.ALL, CampaignAudience.PAST_ATTENDEES):
        for email, name in Order.objects.filter(event__organization=org, status=OrderStatus.PAID,
                                                marketing_opt_in=True).exclude(buyer_email="") \
                .values_list("buyer_email", "buyer_name"):
            contacts.setdefault(email.lower(), name or "")
    blocked = set(Unsubscribe.objects.filter(organization=org).values_list("email", flat=True))
    return {e: n for e, n in contacts.items() if e not in blocked}


def audience_summary(org) -> dict:
    return {
        "followers": Follow.objects.filter(organization=org).count(),
        "past_attendees_opted_in": len(audience_contacts(org, CampaignAudience.PAST_ATTENDEES)),
        "total_reachable": len(audience_contacts(org, CampaignAudience.ALL)),
        "unsubscribed": Unsubscribe.objects.filter(organization=org).count(),
        "daily_limit": settings.CAMPAIGN_DAILY_LIMIT,
        "can_send": org.is_verified,
    }


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------
def queue_campaign(campaign: Campaign) -> Campaign:
    if campaign.status != CampaignStatus.DRAFT:
        raise CampaignError("This campaign has already been sent.")
    if not campaign.organization.is_verified:
        raise CampaignError("Only verified organizers can send campaigns. Request verification in Settings.")
    contacts = audience_contacts(campaign.organization, campaign.audience)
    if not contacts:
        raise CampaignError("No one to send to yet. Followers and attendees who opt in will appear here.")
    with transaction.atomic():
        CampaignRecipient.objects.bulk_create(
            [CampaignRecipient(campaign=campaign, email=e, name=n) for e, n in contacts.items()],
            ignore_conflicts=True,
        )
        campaign.status = CampaignStatus.SENDING
        campaign.recipients_count = len(contacts)
        campaign.queued_at = timezone.now()
        campaign.save(update_fields=["status", "recipients_count", "queued_at", "updated_at"])
    return campaign


def unsubscribe_token(org_id: int, email: str) -> str:
    return signing.dumps({"o": org_id, "e": email.lower()}, salt=UNSUB_SALT, compress=True)


def read_unsubscribe_token(token: str) -> tuple[int, str]:
    data = signing.loads(token, salt=UNSUB_SALT)
    return data["o"], data["e"]


def _send_campaign_email(campaign: Campaign, r: CampaignRecipient):
    org = campaign.organization
    unsub = f"{settings.BACKEND_URL}/u/{unsubscribe_token(org.pk, r.email)}/"
    ev = campaign.event
    ctx = {
        "platform": settings.PLATFORM_NAME, "org": org, "name": (r.name or "").split(" ")[0],
        "paragraphs": [p.strip() for p in campaign.body.replace("\r\n", "\n").split("\n\n") if p.strip()],
        "event": ev, "event_url": f"{settings.FRONTEND_URL}/e/{ev.slug}" if ev else "",
        "when": format_when(ev) if ev else "", "where": format_where(ev) if ev else "", "unsubscribe_url": unsub,
    }
    msg = EmailMultiAlternatives(
        campaign.subject, render_to_string("growth/campaign.txt", ctx),
        f"{org.name} via {settings.PLATFORM_NAME} <{_from_address()}>", [r.email],
        headers={"List-Unsubscribe": f"<{unsub}>"},
    )
    msg.attach_alternative(render_to_string("growth/campaign.html", ctx), "text/html")
    msg.send()


def _from_address() -> str:
    return parseaddr(settings.DEFAULT_FROM_EMAIL)[1]


def sent_today() -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return CampaignRecipient.objects.filter(status=RecipientStatus.SENT, sent_at__gte=start).count()


def process_campaigns() -> int:
    """Send queued campaign emails within today's limit. Returns how many were sent."""
    budget = settings.CAMPAIGN_DAILY_LIMIT - sent_today()
    if budget <= 0:
        return 0
    batch = list(
        CampaignRecipient.objects.filter(status=RecipientStatus.PENDING, campaign__status=CampaignStatus.SENDING)
        .select_related("campaign__organization", "campaign__event__venue")
        .order_by("campaign__queued_at", "id")[:min(budget, 100)]
    )
    sent = 0
    for r in batch:
        c = r.campaign
        if Unsubscribe.objects.filter(organization=c.organization, email=r.email).exists():
            r.status = RecipientStatus.SKIPPED
            r.save(update_fields=["status"])
            continue
        try:
            _send_campaign_email(c, r)
        except Exception as exc:  # noqa: BLE001 - provider errors are recorded per recipient
            logger.exception("Campaign %s to %s failed", c.pk, r.email)
            r.status, r.error = RecipientStatus.FAILED, str(exc)[:300]
            r.save(update_fields=["status", "error"])
            Campaign.objects.filter(pk=c.pk).update(failed_count=F("failed_count") + 1)
            continue
        r.status, r.sent_at = RecipientStatus.SENT, timezone.now()
        r.save(update_fields=["status", "sent_at"])
        Campaign.objects.filter(pk=c.pk).update(sent_count=F("sent_count") + 1)
        sent += 1
    # Close campaigns with nothing left to send.
    for c in Campaign.objects.filter(status=CampaignStatus.SENDING):
        if not c.recipients.filter(status=RecipientStatus.PENDING).exists():
            c.status, c.finished_at = CampaignStatus.SENT, timezone.now()
            c.save(update_fields=["status", "finished_at", "updated_at"])
    return sent


# --------------------------------------------------------------------------
# Automatic messages
# --------------------------------------------------------------------------
def notify_followers_of_new_event(event: Event) -> Campaign | None:
    """When an event is first published, tell the organizer's followers."""
    org = event.organization
    if not Follow.objects.filter(organization=org).exists():
        return None
    campaign = Campaign.objects.create(
        organization=org, event=event, audience=CampaignAudience.FOLLOWERS, automatic=True,
        subject=f"New from {org.name}: {event.title}",
        body=(event.summary or f"{org.name} just announced {event.title}.")
        + "\n\nYou're getting this because you follow them.",
    )
    contacts = audience_contacts(org, CampaignAudience.FOLLOWERS)
    CampaignRecipient.objects.bulk_create(
        [CampaignRecipient(campaign=campaign, email=e, name=n) for e, n in contacts.items()], ignore_conflicts=True,
    )
    campaign.status = CampaignStatus.SENDING if contacts else CampaignStatus.SENT
    campaign.recipients_count = len(contacts)
    campaign.queued_at = timezone.now()
    campaign.save(update_fields=["status", "recipients_count", "queued_at", "updated_at"])
    return campaign


def send_review_requests() -> int:
    """A few hours after an event ends, ask attendees how it was."""
    now = timezone.now()
    orders = Order.objects.select_related("event").filter(
        status=OrderStatus.PAID, review_requested_at__isnull=True, event__status=EventStatus.PUBLISHED,
        event__end_at__lte=now - timedelta(hours=2), event__end_at__gte=now - timedelta(days=3),
    ).exclude(buyer_email="")
    count = 0
    for order in orders:
        ev = order.event
        ctx = {"platform": settings.PLATFORM_NAME, "order": order, "event": ev,
               "review_url": f"{settings.FRONTEND_URL}/e/{ev.slug}#reviews"}
        try:
            msg = EmailMultiAlternatives(
                f"How was {ev.title}?", render_to_string("growth/review_request.txt", ctx),
                settings.DEFAULT_FROM_EMAIL, [order.buyer_email],
            )
            msg.attach_alternative(render_to_string("growth/review_request.html", ctx), "text/html")
            msg.send()
        except Exception:  # noqa: BLE001
            logger.exception("Review request failed for order %s", order.reference)
            continue
        order.review_requested_at = now
        order.save(update_fields=["review_requested_at", "updated_at"])
        count += 1
    return count
