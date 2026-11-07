from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.models import FeeBearer, PlatformSettings
from apps.events.models import Event, EventStatus, PromoCode, TicketType, Venue
from apps.organizations.models import Membership, Organization, PayoutAccount, Role

User = get_user_model()


def future(days=10, hours=0):
    return timezone.now() + timedelta(days=days, hours=hours)


class EventTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com")
        self.org = Organization.objects.create(name="Accra Live", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Role.OWNER)
        self.client.force_authenticate(self.owner)
        self.base = f"/api/v1/organizations/{self.org.slug}/"
        self.venue = Venue.objects.create(
            organization=self.org, name="Accra International Conference Centre",
            city="Accra", region="greater_accra",
        )

    def make_event(self, **kw):
        data = {
            "title": "Afrobeats Night",
            "start_at": future(10).isoformat(),
            "end_at": future(10, 5).isoformat(),
            "venue": self.venue.pk,
            "category": "music",
            **kw,
        }
        res = self.client.post(self.base + "events/", data, format="json")
        assert res.status_code == 201, res.data
        return res.data

    def add_ticket(self, slug, **kw):
        data = {"name": "Regular", "price": "100.00", "quantity": 100, **kw}
        res = self.client.post(f"{self.base}events/{slug}/ticket-types/", data, format="json")
        assert res.status_code == 201, res.data
        return res.data

    def add_payout(self):
        PayoutAccount.objects.create(
            organization=self.org, method="mobile_money", mobile_money_provider="mtn",
            account_number="0241234567", account_name="Accra Live", is_default=True,
        )

    def publish(self, slug):
        return self.client.post(f"{self.base}events/{slug}/publish/")

    def published_event(self, **kw):
        ev = self.make_event(**kw)
        self.add_ticket(ev["slug"])
        self.add_payout()
        assert self.publish(ev["slug"]).status_code == 200
        return ev


class OrganizerEventTests(EventTestBase):
    def test_create_draft(self):
        ev = self.make_event()
        self.assertEqual(ev["status"], "draft")
        self.assertTrue(ev["slug"].startswith("afrobeats-night-"))
        self.assertIn("Add at least one ticket type.", ev["publish_problems"])

    def test_end_must_be_after_start(self):
        res = self.client.post(
            self.base + "events/",
            {"title": "X", "start_at": future(5).isoformat(), "end_at": future(4).isoformat()},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_cannot_use_another_orgs_venue(self):
        other = Organization.objects.create(name="Other")
        v = Venue.objects.create(organization=other, name="Theirs", city="Kumasi", region="ashanti")
        res = self.client.post(
            self.base + "events/",
            {"title": "X", "start_at": future(5).isoformat(), "end_at": future(6).isoformat(), "venue": v.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_publish_requirements(self):
        ev = self.make_event()
        res = self.publish(ev["slug"])
        self.assertEqual(res.status_code, 400)
        self.add_ticket(ev["slug"])
        res = self.publish(ev["slug"])
        self.assertIn("Add a payout account before selling paid tickets.", res.data["problems"])
        self.add_payout()
        res = self.publish(ev["slug"])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "published")
        self.assertIsNotNone(res.data["published_at"])

    def test_free_event_needs_no_payout_account(self):
        ev = self.make_event()
        self.add_ticket(ev["slug"], price="0")
        self.assertEqual(self.publish(ev["slug"]).status_code, 200)

    def test_online_event_needs_link(self):
        ev = self.make_event(format="online", venue=None)
        self.add_ticket(ev["slug"], price="0")
        res = self.publish(ev["slug"])
        self.assertIn("Add the online event link.", res.data["problems"])

    def test_unpublish_and_delete_blocked_after_sales(self):
        ev = self.published_event()
        TicketType.objects.update(quantity_sold=3)
        self.assertEqual(self.client.post(f"{self.base}events/{ev['slug']}/unpublish/").status_code, 400)
        self.assertEqual(self.client.delete(f"{self.base}events/{ev['slug']}/").status_code, 400)

    def test_cancel(self):
        ev = self.published_event()
        url = f"{self.base}events/{ev['slug']}/cancel/"
        self.assertEqual(self.client.post(url, {}).status_code, 400)  # reason required
        res = self.client.post(url, {"reason": "Venue flooded"})
        self.assertEqual(res.data["status"], "cancelled")
        # Cancelled events are frozen.
        self.assertEqual(self.client.patch(f"{self.base}events/{ev['slug']}/", {"title": "Y"}).status_code, 400)
        res = self.client.post(f"{self.base}events/{ev['slug']}/ticket-types/", {"name": "x", "quantity": 1})
        self.assertEqual(res.status_code, 400)

    def test_duplicate(self):
        ev = self.published_event()
        tt = TicketType.objects.get()
        TicketType.objects.update(quantity_sold=5)
        promo = PromoCode.objects.create(event_id=ev["id"], code="early", amount=10, times_used=2)
        promo.ticket_types.add(tt)
        res = self.client.post(f"{self.base}events/{ev['slug']}/duplicate/")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "draft")
        self.assertNotEqual(res.data["slug"], ev["slug"])
        self.assertEqual(res.data["ticket_types"][0]["quantity_sold"], 0)
        copy_promo = PromoCode.objects.get(event__slug=res.data["slug"])
        self.assertEqual(copy_promo.times_used, 0)
        self.assertEqual(copy_promo.ticket_types.get().event.slug, res.data["slug"])

    def test_scanner_can_view_not_edit(self):
        ev = self.make_event()
        scanner = User.objects.create_user(email="scan@example.com")
        Membership.objects.create(organization=self.org, user=scanner, role=Role.SCANNER)
        self.client.force_authenticate(scanner)
        self.assertEqual(self.client.get(self.base + "events/").status_code, 200)
        self.assertEqual(self.client.patch(f"{self.base}events/{ev['slug']}/", {"title": "x"}).status_code, 403)

    def test_outsider_gets_404(self):
        ev = self.make_event()
        self.client.force_authenticate(User.objects.create_user(email="x@example.com"))
        self.assertEqual(self.client.get(f"{self.base}events/{ev['slug']}/").status_code, 404)


class TicketTypeTests(EventTestBase):
    def test_pricing_buyer_pays(self):
        ev = self.make_event()
        t = self.add_ticket(ev["slug"], price="100")
        self.assertEqual(t["pricing"]["fee"], "6.00")
        self.assertEqual(t["pricing"]["buyer_pays"], "106.00")
        self.assertEqual(t["pricing"]["organizer_receives"], "100.00")

    def test_pricing_organizer_absorbs_and_overrides(self):
        self.org.fee_percent_override = Decimal("3")
        self.org.save()
        ev = self.make_event(fee_bearer=FeeBearer.ORGANIZER)
        t = self.add_ticket(ev["slug"], price="100")
        self.assertEqual(t["pricing"]["fee"], "4.00")
        self.assertEqual(t["pricing"]["buyer_pays"], "100.00")
        self.assertEqual(t["pricing"]["organizer_receives"], "96.00")

    def test_free_ticket_has_no_fee(self):
        ev = self.make_event()
        t = self.add_ticket(ev["slug"], price="0")
        self.assertEqual(t["pricing"]["buyer_pays"], "0.00")

    def test_validation(self):
        ev = self.make_event()
        url = f"{self.base}events/{ev['slug']}/ticket-types/"
        bad = [
            {"price": "-1"},
            {"min_per_order": 5, "max_per_order": 2},
            {"sales_start_at": future(3).isoformat(), "sales_end_at": future(2).isoformat()},
            {"sales_end_at": future(30).isoformat()},  # after event ends
        ]
        for extra in bad:
            res = self.client.post(url, {"name": "X", "quantity": 10, **extra}, format="json")
            self.assertEqual(res.status_code, 400, extra)

    def test_cannot_reduce_below_sold_or_delete_sold(self):
        ev = self.make_event()
        t = self.add_ticket(ev["slug"])
        TicketType.objects.update(quantity_sold=40)
        url = f"{self.base}events/{ev['slug']}/ticket-types/{t['id']}/"
        self.assertEqual(self.client.patch(url, {"quantity": 30}).status_code, 400)
        self.assertEqual(self.client.patch(url, {"quantity": 40}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 400)

    def test_sale_status(self):
        ev = self.published_event()
        t = TicketType.objects.get()
        self.assertEqual(t.sale_status, "on_sale")
        t.sales_start_at = future(1)
        self.assertEqual(t.sale_status, "scheduled")
        t.sales_start_at = None
        t.quantity_sold = t.quantity
        self.assertEqual(t.sale_status, "sold_out")


class PromoCodeTests(EventTestBase):
    def test_create_and_normalize(self):
        ev = self.make_event()
        url = f"{self.base}events/{ev['slug']}/promo-codes/"
        res = self.client.post(url, {"code": "early-bird", "discount_type": "percent", "amount": "20"})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["code"], "EARLY-BIRD")
        dup = self.client.post(url, {"code": "Early-Bird", "discount_type": "percent", "amount": "10"})
        self.assertEqual(dup.status_code, 400)

    def test_validation(self):
        ev = self.make_event()
        url = f"{self.base}events/{ev['slug']}/promo-codes/"
        self.assertEqual(self.client.post(url, {"code": "X1", "amount": "10"}).status_code, 400)  # too short
        self.assertEqual(self.client.post(url, {"code": "BIG", "amount": "150"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"code": "FIX", "discount_type": "fixed", "amount": "0"}).status_code, 400)

    def test_cannot_link_other_events_ticket_types(self):
        ev1, ev2 = self.make_event(), self.make_event(title="Other")
        t2 = self.add_ticket(ev2["slug"])
        res = self.client.post(
            f"{self.base}events/{ev1['slug']}/promo-codes/",
            {"code": "SNEAKY", "amount": "10", "ticket_types": [t2["id"]]}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_public_promo_check_and_access_codes(self):
        ev = self.published_event()
        vip = self.add_ticket(ev["slug"], name="VIP Secret", price="500", visibility="hidden")
        promo = PromoCode.objects.create(event_id=ev["id"], code="VIPACCESS", discount_type="percent", amount=10)
        promo.ticket_types.add(vip["id"])
        self.client.force_authenticate(None)

        detail = self.client.get(f"/api/v1/events/{ev['slug']}/").data
        self.assertNotIn("VIP Secret", [t["name"] for t in detail["ticket_types"]])

        res = self.client.post(f"/api/v1/events/{ev['slug']}/promo-check/", {"code": "vipaccess"})
        self.assertEqual(res.status_code, 200)
        [tt] = res.data["ticket_types"]
        self.assertTrue(tt["hidden"])
        self.assertEqual(tt["discounted"]["price"], "450.00")

        self.assertEqual(
            self.client.post(f"/api/v1/events/{ev['slug']}/promo-check/", {"code": "NOPE"}).status_code, 400
        )
        promo.max_uses, promo.times_used = 5, 5
        promo.save()
        res = self.client.post(f"/api/v1/events/{ev['slug']}/promo-check/", {"code": "VIPACCESS"})
        self.assertIn("fully used", str(res.data))

    def test_discount_math(self):
        p = PromoCode(discount_type="fixed", amount=Decimal("150"))
        self.assertEqual(p.discounted_price(Decimal("100")), Decimal("0.00"))
        p = PromoCode(discount_type="percent", amount=Decimal("15"))
        self.assertEqual(p.discounted_price(Decimal("80")), Decimal("68.00"))


class PublicDiscoveryTests(EventTestBase):
    def setUp(self):
        super().setUp()
        self.add_payout()
        kumasi = Venue.objects.create(organization=self.org, name="Baba Yara Stadium", city="Kumasi", region="ashanti")
        self.concert = self._event("Accra Afrobeats Night", self.venue, "music", days=3, price="150")
        self.church = self._event("Kumasi Gospel Praise", kumasi, "church-gospel", days=20, price="0")
        self.draft = Event.objects.create(
            organization=self.org, title="Secret Draft", start_at=future(2), end_at=future(2, 2)
        )
        self.past = Event.objects.create(
            organization=self.org, title="Old Show", status=EventStatus.PUBLISHED,
            start_at=timezone.now() - timedelta(days=3), end_at=timezone.now() - timedelta(days=2),
        )
        self.unlisted = self._event("Private Dinner", self.venue, "food-drink", days=5, price="300")
        self.unlisted.visibility = "unlisted"
        self.unlisted.save()
        self.client.force_authenticate(None)
        PlatformSettings.load()

    def _event(self, title, venue, cat, days, price):
        from apps.events.models import Category

        ev = Event.objects.create(
            organization=self.org, title=title, venue=venue, category=Category.objects.get(slug=cat),
            start_at=future(days), end_at=future(days, 4), status=EventStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        TicketType.objects.create(event=ev, name="Regular", price=Decimal(price), quantity=50)
        return ev

    def titles(self, **params):
        res = self.client.get("/api/v1/events/", params)
        self.assertEqual(res.status_code, 200)
        return [e["title"] for e in res.data["results"]]

    def test_only_published_upcoming_public_events_listed(self):
        self.assertEqual(self.titles(), ["Accra Afrobeats Night", "Kumasi Gospel Praise"])

    def test_filters(self):
        self.assertEqual(self.titles(q="gospel"), ["Kumasi Gospel Praise"])
        self.assertEqual(self.titles(q="baba yara"), ["Kumasi Gospel Praise"])
        self.assertEqual(self.titles(category="music"), ["Accra Afrobeats Night"])
        self.assertEqual(self.titles(region="ashanti"), ["Kumasi Gospel Praise"])
        self.assertEqual(self.titles(city="accra"), ["Accra Afrobeats Night"])
        self.assertEqual(self.titles(price="free"), ["Kumasi Gospel Praise"])
        self.assertEqual(self.titles(price="paid"), ["Accra Afrobeats Night"])
        self.assertEqual(self.titles(when="next_7_days"), ["Accra Afrobeats Night"])
        d = (timezone.localdate() + timedelta(days=15)).isoformat()
        self.assertEqual(self.titles(date_from=d), ["Kumasi Gospel Praise"])
        self.assertEqual(self.client.get("/api/v1/events/", {"date_from": "bad"}).status_code, 400)

    def test_list_card_data(self):
        res = self.client.get("/api/v1/events/", {"category": "music"})
        card = res.data["results"][0]
        self.assertEqual(card["price_from"], "158.50")  # 150 + 5% + GHS 1
        self.assertFalse(card["is_free"])
        self.assertEqual(card["venue"]["city"], "Accra")
        self.assertEqual(card["organizer"]["name"], "Accra Live")

    def test_detail_visibility(self):
        self.assertEqual(self.client.get(f"/api/v1/events/{self.concert.slug}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/events/{self.unlisted.slug}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/events/{self.draft.slug}/").status_code, 404)

    def test_detail_hides_online_link_and_shows_low_stock(self):
        TicketType.objects.filter(event=self.concert).update(quantity_sold=45)
        data = self.client.get(f"/api/v1/events/{self.concert.slug}/").data
        self.assertNotIn("online_url", data)
        self.assertEqual(data["ticket_types"][0]["remaining"], 5)

    def test_cancelled_event_still_viewable_but_not_listed(self):
        self.concert.status = EventStatus.CANCELLED
        self.concert.cancellation_reason = "Artist unwell"
        self.concert.save()
        self.assertNotIn("Accra Afrobeats Night", self.titles())
        data = self.client.get(f"/api/v1/events/{self.concert.slug}/").data
        self.assertEqual(data["cancellation_reason"], "Artist unwell")

    def test_inactive_organizer_hidden(self):
        self.org.is_active = False
        self.org.save()
        self.assertEqual(self.titles(), [])

    def test_categories(self):
        res = self.client.get("/api/v1/categories/")
        self.assertIn("church-gospel", [c["slug"] for c in res.data])
