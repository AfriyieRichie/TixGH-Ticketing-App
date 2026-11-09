from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.growth import services
from apps.growth.models import Campaign, CampaignRecipient, TrackingLink, Unsubscribe
from apps.orders.models import Order
from apps.orders.services import create_order, fulfil_order
from apps.organizations.models import Membership, Organization, PayoutAccount, Role, VerificationStatus

User = get_user_model()


class GrowthBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com")
        self.org = Organization.objects.create(name="Accra Live", verification_status=VerificationStatus.VERIFIED)
        Membership.objects.create(organization=self.org, user=self.owner, role=Role.OWNER)
        PayoutAccount.objects.create(organization=self.org, method="mobile_money", mobile_money_provider="mtn",
                                     account_number="0241234567", account_name="A", is_default=True)
        self.venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra")
        self.event = self.make_event("Afrobeats Night", days=5)
        self.tt = TicketType.objects.create(event=self.event, name="Regular", price=Decimal("100"), quantity=100)
        self.org_base = f"/api/v1/organizations/{self.org.slug}/"

    def make_event(self, title, days, **kw):
        now = timezone.now()
        return Event.objects.create(organization=self.org, title=title, venue=self.venue, status=EventStatus.PUBLISHED,
                                    start_at=now + timedelta(days=days), end_at=now + timedelta(days=days, hours=5),
                                    published_at=now, **kw)

    def buy(self, email, opt_in=False, ref="", event=None, qty=1):
        event = event or self.event
        tt = event.ticket_types.first()
        o = create_order(event=event, items=[{"ticket_type": tt.pk, "quantity": qty}], ref=ref,
                         buyer={"full_name": email.split("@")[0].title(), "email": email, "marketing_opt_in": opt_in})
        return fulfil_order(o, amount_paid=o.total)


class FollowTests(GrowthBase):
    def test_follow_unfollow_and_profile_count(self):
        url = f"/api/v1/organizations/public/{self.org.slug}/follow/"
        self.assertEqual(self.client.get(url).data, {"following": False, "followers": 0})
        self.assertEqual(self.client.post(url).status_code, 401)
        fan = User.objects.create_user(email="fan@example.com")
        self.client.force_authenticate(fan)
        self.assertEqual(self.client.post(url).data, {"following": True, "followers": 1})
        self.assertEqual(self.client.get("/api/v1/me/following/").data[0]["slug"], self.org.slug)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/v1/organizations/public/{self.org.slug}/").data["followers"], 1)
        self.client.force_authenticate(fan)
        self.assertEqual(self.client.delete(url).data["following"], False)

    def test_first_publish_emails_followers(self):
        fan = User.objects.create_user(email="fan@example.com", full_name="Ama Fan")
        self.client.force_authenticate(fan)
        self.client.post(f"/api/v1/organizations/public/{self.org.slug}/follow/")
        now = timezone.now()
        draft = Event.objects.create(organization=self.org, title="Comedy Jam", venue=self.venue,
                                     start_at=now + timedelta(days=9), end_at=now + timedelta(days=9, hours=3))
        TicketType.objects.create(event=draft, name="Free", price=0, quantity=10)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f"{self.org_base}events/{draft.slug}/publish/").status_code, 200)
        campaign = Campaign.objects.get(automatic=True)
        self.assertEqual(campaign.recipients_count, 1)
        services.process_campaigns()
        self.assertEqual(mail.outbox[-1].to, ["fan@example.com"])
        self.assertIn("Comedy Jam", mail.outbox[-1].subject)
        # Unpublish + republish doesn't email again.
        self.client.post(f"{self.org_base}events/{draft.slug}/unpublish/")
        self.client.post(f"{self.org_base}events/{draft.slug}/publish/")
        self.assertEqual(Campaign.objects.filter(automatic=True).count(), 1)


class TrackingLinkTests(GrowthBase):
    def test_attribution_and_stats(self):
        self.client.force_authenticate(self.owner)
        base = f"{self.org_base}events/{self.event.slug}/tracking-links/"
        res = self.client.post(base, {"code": "KOFI", "label": "Kofi (influencer)", "commission_percent": "10"})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["url"].endswith(f"/e/{self.event.slug}?ref=kofi"))
        self.assertEqual(self.client.post(base, {"code": "kofi", "label": "dup"}).status_code, 400)

        self.client.force_authenticate(None)
        for _ in range(3):
            self.client.post(f"/api/v1/events/{self.event.slug}/ref/KOFI/")
        self.assertFalse(self.client.post(f"/api/v1/events/{self.event.slug}/ref/nobody/").data["valid"])
        self.buy("a@example.com", ref="Kofi", qty=2)
        self.buy("b@example.com", ref="unknown")
        self.client.force_authenticate(self.owner)
        [link] = self.client.get(base).data
        self.assertEqual((link["clicks"], link["orders"], link["tickets"]), (3, 1, 2))
        self.assertEqual((link["revenue"], link["commission"]), ("200.00", "20.00"))
        self.assertEqual(self.client.delete(f"{base}{link['id']}/").status_code, 400)  # has sales

    def test_checkout_api_accepts_ref(self):
        TrackingLink.objects.create(event=self.event, code="ig", label="Instagram")
        res = self.client.post("/api/v1/checkout/", {
            "event": self.event.slug, "items": [{"ticket_type": self.tt.pk, "quantity": 1}], "ref": "IG",
            "buyer": {"full_name": "X", "phone": "0241112222", "marketing_opt_in": True},
        }, format="json")
        order = Order.objects.get(reference=res.data["reference"])
        self.assertEqual(order.tracking_link.code, "ig")
        self.assertTrue(order.marketing_opt_in)


class CampaignTests(GrowthBase):
    def setUp(self):
        super().setUp()
        self.buy("yes@example.com", opt_in=True)
        self.buy("no@example.com", opt_in=False)
        fan = User.objects.create_user(email="fan@example.com")
        self.client.force_authenticate(fan)
        self.client.post(f"/api/v1/organizations/public/{self.org.slug}/follow/")
        self.client.force_authenticate(self.owner)

    def create(self, **kw):
        res = self.client.post(f"{self.org_base}campaigns/", {
            "subject": "Our next show", "body": "Hello!\n\nIt's going to be big.", "event": self.event.slug, **kw,
        })
        assert res.status_code == 201, res.data
        return res.data

    def test_audience_respects_opt_in(self):
        a = self.client.get(f"{self.org_base}audience/").data
        self.assertEqual((a["followers"], a["past_attendees_opted_in"], a["total_reachable"]), (1, 1, 2))
        self.assertTrue(a["can_send"])

    def test_send_with_unsubscribe(self):
        c = self.create()
        mail.outbox.clear()
        res = self.client.post(f"{self.org_base}campaigns/{c['id']}/send/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["sent_count"]), ("sent", 2))
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["fan@example.com", "yes@example.com"])
        msg = mail.outbox[0]
        self.assertIn("Get tickets", msg.alternatives[0][0])
        unsub_url = msg.extra_headers["List-Unsubscribe"].strip("<>")
        path = unsub_url.split("127.0.0.1:8000")[-1]
        self.assertContains(self.client.get(path), "Unsubscribe from Accra Live?")
        self.assertContains(self.client.post(path), "You're unsubscribed")
        self.assertTrue(Unsubscribe.objects.filter(email=msg.to[0]).exists())
        # Next campaign skips them, and sent campaigns are locked.
        self.assertEqual(self.client.get(f"{self.org_base}audience/").data["total_reachable"], 1)
        self.assertEqual(self.client.post(f"{self.org_base}campaigns/{c['id']}/send/").status_code, 400)
        self.assertEqual(self.client.patch(f"{self.org_base}campaigns/{c['id']}/", {"subject": "x"}).status_code, 400)

    def test_unverified_organizer_cannot_send(self):
        Organization.objects.filter(pk=self.org.pk).update(verification_status=VerificationStatus.UNVERIFIED)
        c = self.create()
        res = self.client.post(f"{self.org_base}campaigns/{c['id']}/send/")
        self.assertIn("verified", str(res.data))

    @override_settings(CAMPAIGN_DAILY_LIMIT=1)
    def test_daily_limit_continues_later(self):
        c = self.create()
        res = self.client.post(f"{self.org_base}campaigns/{c['id']}/send/")
        self.assertEqual((res.data["status"], res.data["sent_count"]), ("sending", 1))
        self.assertEqual(services.process_campaigns(), 0)  # today's budget used
        CampaignRecipient.objects.filter(status="sent").update(sent_at=timezone.now() - timedelta(days=1))
        self.assertEqual(services.process_campaigns(), 1)
        self.assertEqual(Campaign.objects.get(pk=c["id"]).status, "sent")

    def test_bad_unsubscribe_token(self):
        self.assertEqual(self.client.get("/u/not-a-token/").status_code, 400)


class ReviewTests(GrowthBase):
    def test_only_attendees_after_start(self):
        buyer = User.objects.create_user(email="buyer@example.com", full_name="Ama Mensah")
        order = self.buy("buyer@example.com")
        Order.objects.filter(pk=order.pk).update(user=buyer)
        url = f"/api/v1/events/{self.event.slug}/reviews/"
        self.client.force_authenticate(buyer)
        self.assertEqual(self.client.post(url, {"rating": 5}).status_code, 403)  # not started yet
        Event.objects.filter(pk=self.event.pk).update(start_at=timezone.now() - timedelta(hours=5),
                                                      end_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.client.post(url, {"rating": 6}).status_code, 400)
        self.assertEqual(self.client.post(url, {"rating": 4, "comment": "Great sound"}).status_code, 201)
        self.client.post(url, {"rating": 5, "comment": "Updated"})  # editing keeps one review
        data = self.client.get(url).data
        self.assertEqual((data["average"], data["count"], data["reviews"][0]["author"]), (5.0, 1, "Ama M."))
        stranger = User.objects.create_user(email="x@example.com")
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.post(url, {"rating": 1}).status_code, 403)
        # Organizer replies; rating shows on the public profile.
        self.client.force_authenticate(self.owner)
        rid = data["reviews"][0]["id"]
        res = self.client.post(f"{self.org_base}events/{self.event.slug}/reviews/{rid}/reply/", {"reply": "Thank you!"})
        self.assertEqual(res.data["organizer_reply"], "Thank you!")
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/v1/organizations/public/{self.org.slug}/").data["rating"]["average"], 5.0)

    def test_review_request_email_once(self):
        self.buy("buyer@example.com")
        Event.objects.filter(pk=self.event.pk).update(start_at=timezone.now() - timedelta(hours=8),
                                                      end_at=timezone.now() - timedelta(hours=3))
        mail.outbox.clear()
        self.assertEqual(services.send_review_requests(), 1)
        self.assertIn("How was Afrobeats Night", mail.outbox[0].subject)
        self.assertEqual(services.send_review_requests(), 0)


class DiscoveryTests(GrowthBase):
    def test_trending_and_similar(self):
        quiet = self.make_event("Quiet Talk", days=1)
        TicketType.objects.create(event=quiet, name="Free", price=0, quantity=10)
        self.buy("a@example.com", qty=3)
        self.buy("b@example.com")
        titles = [e["title"] for e in self.client.get("/api/v1/events/", {"sort": "trending"}).data["results"]]
        self.assertEqual(titles[0], "Afrobeats Night")
        sim = self.client.get(f"/api/v1/events/{self.event.slug}/similar/").data
        self.assertEqual([e["title"] for e in sim], ["Quiet Talk"])  # same organizer
