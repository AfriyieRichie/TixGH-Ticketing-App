from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.checkin.models import CheckIn
from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.orders.models import Ticket, TicketStatus
from apps.orders.services import create_order, fulfil_order
from apps.organizations.models import Membership, Organization, Role
from apps.tickets.models import TicketTransfer
from apps.tickets.signing import qr_payload

User = get_user_model()


class CheckInBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Accra Live")
        self.scanner = User.objects.create_user(email="gate@example.com")
        Membership.objects.create(organization=self.org, user=self.scanner, role=Role.SCANNER)
        venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra")
        now = timezone.now()
        self.event = Event.objects.create(
            organization=self.org, title="Afrobeats Night", venue=venue, status=EventStatus.PUBLISHED,
            start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=6),
        )
        self.table = TicketType.objects.create(event=self.event, name="Table", price=Decimal("0"), quantity=5, admits=8)
        self.free = TicketType.objects.create(event=self.event, name="Free", price=Decimal("0"), quantity=50)
        order = create_order(event=self.event, items=[{"ticket_type": self.free.pk, "quantity": 2},
                                                      {"ticket_type": self.table.pk, "quantity": 1}],
                             buyer={"full_name": "Ama Mensah", "phone": "0241112222"})
        fulfil_order(order, amount_paid=order.total)
        self.t1, self.t2 = Ticket.objects.filter(ticket_type=self.free)
        self.client.force_authenticate(self.scanner)
        self.base = f"/api/v1/scanner/events/{self.event.slug}/"

    def scan(self, raw, **kw):
        return self.client.post(self.base + "scan/", {"raw": raw, "gate": "Gate A", **kw}, format="json")


class ScanTests(CheckInBase):
    def test_admit_then_duplicate(self):
        res = self.scan(qr_payload(self.t1))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"], "ok")
        self.assertEqual(res.data["ticket"]["name"], "Ama Mensah")
        self.assertEqual(res.data["stats"]["checked_in"], 1)
        res = self.scan(qr_payload(self.t1), gate="Gate B")
        self.assertEqual(res.data["result"], "duplicate")
        self.assertEqual(res.data["previous"]["gate"], "Gate A")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TicketStatus.CHECKED_IN)
        self.assertEqual(CheckIn.objects.count(), 2)

    def test_typed_code_works(self):
        self.assertEqual(self.scan(self.t2.code.lower()).data["result"], "ok")

    def test_forged_and_unknown(self):
        forged = f"TX1:{self.t1.code}:AAAAAAAAAAAA"
        self.assertEqual(self.scan(forged).data["result"], "invalid")
        self.assertEqual(self.scan("ZZZZZZZZZZ").data["result"], "invalid")
        self.assertEqual(self.scan("hello world").data["result"], "invalid")

    def test_other_events_ticket(self):
        other = Event.objects.create(organization=self.org, title="Other", status=EventStatus.PUBLISHED,
                                     start_at=self.event.start_at, end_at=self.event.end_at)
        tt = TicketType.objects.create(event=other, name="X", price=0, quantity=5)
        o = create_order(event=other, items=[{"ticket_type": tt.pk, "quantity": 1}], buyer={"full_name": "K", "phone": "0201111111"})
        fulfil_order(o, amount_paid=o.total)
        foreign = o.tickets.get()
        self.assertEqual(self.scan(qr_payload(foreign)).data["result"], "wrong_event")
        self.assertEqual(self.scan(foreign.code).data["result"], "wrong_event")

    def test_transferred_old_code(self):
        TicketTransfer.objects.create(ticket=self.t1, to_name="K", to_contact="+233200000000",
                                      old_code="OLDCODE234", new_code=self.t1.code)
        self.assertEqual(self.scan("OLDCODE234").data["result"], "transferred")

    def test_void_and_cancelled(self):
        Ticket.objects.filter(pk=self.t1.pk).update(status=TicketStatus.VOID)
        self.assertEqual(self.scan(self.t1.code).data["result"], "void")
        Event.objects.filter(pk=self.event.pk).update(status=EventStatus.CANCELLED)
        self.assertEqual(self.scan(self.t2.code).data["result"], "event_cancelled")

    def test_people_count_includes_tables(self):
        table = Ticket.objects.get(ticket_type=self.table)
        stats = self.scan(table.code).data["stats"]
        self.assertEqual((stats["tickets"], stats["checked_in"], stats["people"], stats["people_in"]), (3, 1, 10, 8))


class PermissionTests(CheckInBase):
    def test_roles(self):
        for role, allowed in [(Role.FINANCE, False), (Role.MARKETING, False), (Role.ADMIN, True)]:
            u = User.objects.create_user(email=f"{role}@example.com")
            Membership.objects.create(organization=self.org, user=u, role=role)
            self.client.force_authenticate(u)
            self.assertEqual(self.scan(self.t1.code).status_code == 200, allowed, role)
            self.assertEqual(self.client.get(self.base + "manifest/").status_code == 200, allowed, role)
        self.client.force_authenticate(User.objects.create_user(email="stranger@example.com"))
        self.assertEqual(self.scan(self.t2.code).status_code, 403)

    def test_events_list_only_scannable(self):
        Organization.objects.create(name="Not mine")
        res = self.client.get("/api/v1/scanner/events/")
        self.assertEqual([e["slug"] for e in res.data], [self.event.slug])
        self.assertEqual(res.data[0]["stats"]["tickets"], 3)


class ManifestAndSyncTests(CheckInBase):
    def test_full_then_delta(self):
        res = self.client.get(self.base + "manifest/")
        self.assertTrue(res.data["full"])
        self.assertEqual(len(res.data["tickets"]), 3)
        self.assertTrue(res.data["key"])
        since = res.data["server_time"]
        Ticket.objects.filter(pk=self.t1.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        Ticket.objects.filter(pk=self.t2.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        Ticket.objects.filter(ticket_type=self.table).update(updated_at=timezone.now() - timedelta(hours=1))
        self.scan(self.t1.code)  # changes t1 only
        delta = self.client.get(self.base + "manifest/", {"since": since}).data
        self.assertFalse(delta["full"])
        self.assertEqual([t["code"] for t in delta["tickets"]], [self.t1.code])
        self.assertEqual(delta["tickets"][0]["status"], "checked_in")

    def test_offline_sync_detects_cross_gate_duplicates(self):
        now = timezone.now()
        # Gate B (online) admitted t1 first; Gate A (offline) scanned it later and syncs now.
        self.scan(self.t1.code, gate="Gate B", scanned_at=(now - timedelta(minutes=5)).isoformat())
        res = self.client.post(self.base + "sync/", {"device_id": "phone-A", "scans": [
            {"client_id": "a2", "raw": qr_payload(self.t2), "gate": "Gate A", "scanned_at": (now - timedelta(minutes=1)).isoformat()},
            {"client_id": "a1", "raw": qr_payload(self.t1), "gate": "Gate A", "scanned_at": (now - timedelta(minutes=2)).isoformat()},
        ]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        by_id = {r["client_id"]: r for r in res.data["results"]}
        self.assertEqual(by_id["a2"]["result"], "ok")
        self.assertEqual(by_id["a1"]["result"], "duplicate")
        self.assertEqual(by_id["a1"]["previous"]["gate"], "Gate B")
        self.assertEqual(res.data["stats"]["checked_in"], 2)
        self.assertEqual(CheckIn.objects.filter(device_id="phone-A").count(), 2)

    def test_future_timestamps_are_clamped(self):
        future = (timezone.now() + timedelta(days=2)).isoformat()
        self.scan(self.t1.code, scanned_at=future)
        self.t1.refresh_from_db()
        self.assertLessEqual(self.t1.checked_in_at, timezone.now())


class UndoTests(CheckInBase):
    def test_scanner_can_undo_own_recent_scan_only(self):
        self.scan(self.t1.code)
        res = self.client.post(self.base + "undo/", {"code": self.t1.code})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["ticket"]["status"], "valid")
        # Someone else's scan can't be undone by a scanner...
        other = User.objects.create_user(email="gate2@example.com")
        Membership.objects.create(organization=self.org, user=other, role=Role.SCANNER)
        self.scan(self.t1.code)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.base + "undo/", {"code": self.t1.code}).status_code, 400)
        # ...but an admin can.
        admin = User.objects.create_user(email="admin@example.com")
        Membership.objects.create(organization=self.org, user=admin, role=Role.ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.post(self.base + "undo/", {"code": self.t1.code}).status_code, 200)
        # After an undo, the ticket can be admitted again.
        self.client.force_authenticate(self.scanner)
        self.assertEqual(self.scan(self.t1.code).data["result"], "ok")
