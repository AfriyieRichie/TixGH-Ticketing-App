from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.orders.models import Ticket
from apps.organizations.models import Membership, Organization, PayoutAccount, Role

User = get_user_model()


class BadgeTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Africa Prosperity Network")
        PayoutAccount.objects.create(organization=self.org, method="mobile_money", mobile_money_provider="mtn",
                                     account_number="0241234567", account_name="APN", is_default=True)
        venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra")
        now = timezone.now()
        self.event = Event.objects.create(
            organization=self.org, title="Africa Prosperity Dialogues", venue=venue, status=EventStatus.PUBLISHED,
            start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=9),
            badges_enabled=True, badge_event_code="APD2026",
        )
        self.delegate = TicketType.objects.create(event=self.event, name="Standard", price=Decimal("0"), quantity=100,
                                                  badge_role="Delegate", wristband_color="gold")
        self.desk = User.objects.create_user(email="desk@example.com")
        Membership.objects.create(organization=self.org, user=self.desk, role=Role.SCANNER)
        self.base = f"/api/v1/scanner/events/{self.event.slug}/"

    def register(self, name, share=True, org="Nexus BI", title="Analyst", phone="0241112222"):
        res = self.client.post("/api/v1/checkout/", {
            "event": self.event.slug, "items": [{"ticket_type": self.delegate.pk, "quantity": 1}],
            "buyer": {"full_name": name, "phone": phone, "email": "eric@example.com",
                      "organization": org, "job_title": title, "share_contact": share},
        }, format="json")
        assert res.status_code == 201, res.data
        return Ticket.objects.get(order__reference=res.data["reference"])

    def test_registration_details_reach_the_ticket(self):
        t = self.register("Eric Boateng Siaw")
        self.assertEqual((t.attendee_organization, t.attendee_job_title, t.share_contact), ("Nexus BI", "Analyst", True))

    def test_contact_sharing_ignored_when_event_has_no_badges(self):
        Event.objects.filter(pk=self.event.pk).update(badges_enabled=False)
        self.event.refresh_from_db()
        self.assertFalse(self.register("Ama").share_contact)

    def test_scan_then_desk_queue_then_print(self):
        t = self.register("Eric Boateng Siaw")
        self.client.force_authenticate(self.desk)
        # Nothing to print until the person is admitted at the door.
        self.assertEqual(self.client.get(self.base + "badges/").data["badges"], [])
        scan = self.client.post(self.base + "scan/", {"raw": t.code}, format="json").data
        self.assertEqual(scan["ticket"]["role"], "Delegate")
        self.assertEqual(scan["ticket"]["wristband"], {"color": "gold", "label": "Gold", "hex": "#CA8A04"})

        queue = self.client.get(self.base + "badges/").data
        self.assertEqual(queue["event"]["code"], "APD2026")
        [badge] = queue["badges"]
        self.assertEqual((badge["name"], badge["organization"], badge["role"]), ("Eric Boateng Siaw", "Nexus BI", "Delegate"))
        self.assertIn("BEGIN:VCARD", badge["qr"])
        self.assertIn("ORG:Nexus BI", badge["qr"])
        self.assertIn("TEL;TYPE=CELL:+233241112222", badge["qr"])

        printed = self.client.post(f"{self.base}badges/{t.code}/printed/").data
        self.assertEqual(printed["print_count"], 1)
        self.assertEqual(self.client.get(self.base + "badges/").data["badges"], [])
        self.assertEqual(len(self.client.get(self.base + "badges/", {"status": "printed"}).data["badges"]), 1)
        # Reprint counts up.
        self.assertEqual(self.client.post(f"{self.base}badges/{t.code}/printed/").data["print_count"], 2)

    def test_no_contact_in_qr_without_consent(self):
        t = self.register("Private Person", share=False)
        self.client.force_authenticate(self.desk)
        self.client.post(self.base + "scan/", {"raw": t.code}, format="json")
        self.assertIsNone(self.client.get(self.base + "badges/").data["badges"][0]["qr"])

    def test_search_for_preprinting(self):
        self.register("Eric Boateng Siaw")
        self.register("Kofi Mensah", org="Ghana Tech")
        self.client.force_authenticate(self.desk)
        res = self.client.get(self.base + "badges/", {"q": "ghana tech"})
        self.assertEqual([b["name"] for b in res.data["badges"]], ["Kofi Mensah"])

    def test_desk_can_fix_names_but_only_managers_change_roles(self):
        t = self.register("Eric Boatng")
        self.client.force_authenticate(self.desk)
        res = self.client.patch(f"{self.base}badges/{t.code}/", {"attendee_name": "Eric Boateng Siaw"}, format="json")
        self.assertEqual(res.data["name"], "Eric Boateng Siaw")
        self.assertEqual(self.client.patch(f"{self.base}badges/{t.code}/", {"badge_role": "Speaker"}, format="json").status_code, 403)
        admin = User.objects.create_user(email="admin@example.com")
        Membership.objects.create(organization=self.org, user=admin, role=Role.ADMIN)
        self.client.force_authenticate(admin)
        res = self.client.patch(f"{self.base}badges/{t.code}/", {"badge_role": "Speaker"}, format="json")
        self.assertEqual(res.data["role"], "Speaker")

    def test_attendee_can_update_badge_details_in_wallet(self):
        user = User.objects.create_user(phone="0241112222", phone_verified=True, full_name="Eric")
        self.client.force_authenticate(user)
        res = self.client.post("/api/v1/checkout/", {
            "event": self.event.slug, "items": [{"ticket_type": self.delegate.pk, "quantity": 1}], "buyer": {},
        }, format="json")
        code = res.data["tickets"][0]["code"]
        res = self.client.patch(f"/api/v1/tickets/{code}/", {"attendee_organization": "Nexus BI", "share_contact": False}, format="json")
        self.assertEqual((res.data["attendee_organization"], res.data["share_contact"]), ("Nexus BI", False))
