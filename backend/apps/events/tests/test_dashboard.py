from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.orders.models import Ticket, TicketStatus
from apps.orders.services import create_order, fulfil_order
from apps.organizations.models import Membership, Organization, PayoutAccount, Role

User = get_user_model()


class DashboardTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com")
        self.org = Organization.objects.create(name="Accra Live")
        Membership.objects.create(organization=self.org, user=self.owner, role=Role.OWNER)
        PayoutAccount.objects.create(organization=self.org, method="mobile_money", mobile_money_provider="mtn",
                                     account_number="0241234567", account_name="A", is_default=True)
        venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra")
        now = timezone.now()
        self.event = Event.objects.create(
            organization=self.org, title="Afrobeats Night", venue=venue, status=EventStatus.PUBLISHED,
            start_at=now + timedelta(days=5), end_at=now + timedelta(days=5, hours=5),
        )
        self.regular = TicketType.objects.create(event=self.event, name="Regular", price=Decimal("100"), quantity=50)
        self.vip = TicketType.objects.create(event=self.event, name="VIP", price=Decimal("500"), quantity=10)
        for name, phone, items in [
            ("Ama Mensah", "0241112222", [{"ticket_type": self.regular.pk, "quantity": 2}]),
            ("Kofi Owusu", "0559998888", [{"ticket_type": self.vip.pk, "quantity": 1}]),
        ]:
            order = create_order(event=self.event, items=items, buyer={"full_name": name, "phone": phone})
            fulfil_order(order, amount_paid=order.total)
        # An unpaid order must not count.
        create_order(event=self.event, items=[{"ticket_type": self.regular.pk, "quantity": 1}],
                     buyer={"full_name": "Pending", "phone": "0201111111"})
        Ticket.objects.filter(order__buyer_name="Kofi Owusu").update(status=TicketStatus.CHECKED_IN)
        self.client.force_authenticate(self.owner)
        self.base = f"/api/v1/organizations/{self.org.slug}/"

    def test_overview(self):
        d = self.client.get(self.base + "overview/").data
        self.assertEqual(d["orders"], 2)
        self.assertEqual(d["tickets_sold"], 3)
        self.assertEqual(d["organizer_earnings"], "700.00")
        self.assertEqual(d["gross_sales"], "738.00")  # 2x106 + 526
        self.assertEqual(d["events"]["upcoming"], 1)
        self.assertEqual(d["top_events"][0]["title"], "Afrobeats Night")
        self.assertEqual(len(d["recent_orders"]), 2)

    def test_event_stats(self):
        d = self.client.get(f"{self.base}events/{self.event.slug}/stats/").data
        self.assertEqual(d["tickets_sold"], 3)
        self.assertEqual(d["checked_in"], 1)
        self.assertEqual(d["capacity"], 60)
        self.assertEqual(d["pending_orders"], 1)
        vip = next(t for t in d["ticket_types"] if t["name"] == "VIP")
        self.assertEqual((vip["sold"], vip["checked_in"], vip["earnings"]), (1, 1, "500.00"))
        self.assertEqual(sum(day["orders"] for day in d["daily"]), 2)

    def test_attendees_search_and_csv(self):
        url = f"{self.base}events/{self.event.slug}/attendees/"
        self.assertEqual(self.client.get(url).data["count"], 3)
        self.assertEqual(self.client.get(url, {"q": "kofi"}).data["count"], 1)
        self.assertEqual(self.client.get(url, {"q": "0241112222"}).data["count"], 2)
        self.assertEqual(self.client.get(url, {"status": "checked_in"}).data["count"], 1)
        res = self.client.get(url, {"export": "csv"})
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")
        lines = res.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Ticket code,Ticket type"))

    def test_scanner_cannot_see_sales(self):
        scanner = User.objects.create_user(email="scan@example.com")
        Membership.objects.create(organization=self.org, user=scanner, role=Role.SCANNER)
        self.client.force_authenticate(scanner)
        self.assertEqual(self.client.get(self.base + "overview/").status_code, 403)
        self.assertEqual(self.client.get(f"{self.base}events/{self.event.slug}/attendees/").status_code, 403)

    def test_finance_can_see_sales(self):
        fin = User.objects.create_user(email="fin@example.com")
        Membership.objects.create(organization=self.org, user=fin, role=Role.FINANCE)
        self.client.force_authenticate(fin)
        self.assertEqual(self.client.get(self.base + "overview/").status_code, 200)
