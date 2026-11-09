from datetime import timedelta

from django.utils import timezone

from apps.events.models import Event
from apps.orders.models import Ticket
from apps.tickets.signing import qr_payload

from .test_checkin import CheckInBase


class ReentryTests(CheckInBase):
    def allow(self, **kw):
        Event.objects.filter(pk=self.event.pk).update(reentry_allowed=True, **kw)
        self.event.refresh_from_db()

    def out(self, raw, **kw):
        return self.scan(raw, direction="out", **kw)

    def test_no_reentry_by_default(self):
        self.assertEqual(self.scan(self.t1.code).data["result"], "ok")
        # Still inside: same QR is refused (screenshot shared to a friend).
        self.assertEqual(self.scan(self.t1.code).data["result"], "duplicate")
        # Leaves; exit is recorded but the event doesn't allow coming back.
        res = self.out(self.t1.code)
        self.assertEqual(res.data["result"], "exit")
        self.assertIn("No re-entry", res.data["message"])
        res = self.scan(self.t1.code)
        self.assertEqual(res.data["result"], "no_reentry")
        self.assertEqual(res.data["stats"]["people_in"], 0)

    def test_scan_out_and_back_in(self):
        self.allow()
        self.scan(self.t1.code)
        self.assertEqual(self.out(self.t1.code).data["ticket"]["inside"], 0)
        res = self.scan(self.t1.code)
        self.assertEqual(res.data["result"], "reentry")
        self.assertEqual(res.data["ticket"]["reentries"], 1)
        self.assertEqual(res.data["stats"]["people_in"], 1)
        # While back inside, the QR can't let a second person in.
        self.assertEqual(self.scan(self.t1.code).data["result"], "duplicate")

    def test_exit_when_not_inside(self):
        self.allow()
        self.assertEqual(self.out(self.t1.code).data["result"], "not_inside")

    def test_max_reentries(self):
        self.allow(max_reentries=1)
        self.scan(self.t1.code)
        self.out(self.t1.code)
        self.assertEqual(self.scan(self.t1.code).data["result"], "reentry")
        self.out(self.t1.code)
        res = self.scan(self.t1.code)
        self.assertEqual(res.data["result"], "no_reentry")
        self.assertIn("limit reached", res.data["message"])

    def test_reentry_cutoff(self):
        self.allow(reentry_cutoff_at=timezone.now() - timedelta(minutes=1))
        self.scan(self.t1.code, scanned_at=(timezone.now() - timedelta(hours=1)).isoformat())
        self.out(self.t1.code)
        res = self.scan(self.t1.code)
        self.assertEqual(res.data["result"], "no_reentry")
        self.assertIn("closed", res.data["message"])

    def test_group_ticket_partial_arrival_and_exit(self):
        self.allow()
        table = Ticket.objects.get(ticket_type=self.table)  # admits 8
        res = self.scan(qr_payload(table), count=3)
        self.assertEqual((res.data["result"], res.data["ticket"]["admitted"], res.data["ticket"]["inside"]), ("ok", 3, 3))
        self.assertIn("3 of 8", res.data["message"])
        # The other 5 arrive later on the same QR (default = everyone not yet in).
        res = self.scan(table.code)
        self.assertEqual((res.data["ticket"]["admitted"], res.data["ticket"]["inside"]), (8, 8))
        self.assertEqual(self.scan(table.code).data["result"], "duplicate")
        # 2 step out and come back.
        self.assertEqual(self.out(table.code, count=2).data["ticket"]["inside"], 6)
        res = self.scan(table.code)
        self.assertEqual((res.data["result"], res.data["people"], res.data["ticket"]["inside"]), ("reentry", 2, 8))

    def test_group_without_reentry_lets_late_arrivals_in_only(self):
        table = Ticket.objects.get(ticket_type=self.table)
        self.scan(table.code, count=3)
        self.out(table.code, count=1)
        # 5 newcomers + 1 returner want in: newcomers are allowed, the returner isn't.
        res = self.scan(table.code, count=6)
        self.assertEqual(res.data["result"], "ok")
        self.assertEqual((res.data["ticket"]["admitted"], res.data["ticket"]["inside"]), (8, 7))
        self.assertIn("no re-entry", res.data["message"])

    def test_undo_exit_and_entry(self):
        self.allow()
        self.scan(self.t1.code)
        self.out(self.t1.code)
        res = self.client.post(self.base + "undo/", {"code": self.t1.code})  # undo the exit
        self.assertEqual(res.data["ticket"]["inside"], 1)
        res = self.client.post(self.base + "undo/", {"code": self.t1.code})  # undo the entry
        self.assertEqual((res.data["ticket"]["status"], res.data["ticket"]["admitted"]), ("valid", 0))

    def test_offline_sync_with_exits(self):
        self.allow()
        now = timezone.now()
        res = self.client.post(self.base + "sync/", {"scans": [
            {"client_id": "1", "raw": self.t1.code, "scanned_at": (now - timedelta(minutes=30)).isoformat()},
            {"client_id": "2", "raw": self.t1.code, "direction": "out", "scanned_at": (now - timedelta(minutes=20)).isoformat()},
            {"client_id": "3", "raw": self.t1.code, "scanned_at": (now - timedelta(minutes=10)).isoformat()},
        ]}, format="json")
        self.assertEqual([r["result"] for r in res.data["results"]], ["ok", "exit", "reentry"])

    def test_qr_stays_visible_after_entry_only_when_reentry_allowed(self):
        self.client.force_authenticate(None)
        url = f"/api/v1/orders/{self.t1.order.reference}/"
        params = {"token": self.t1.order.access_token}
        self.client.force_authenticate(self.scanner)
        self.scan(self.t1.code)
        self.client.force_authenticate(None)
        qr = lambda: next(t for t in self.client.get(url, params).data["tickets"] if t["code"] == self.t1.code)["qr_payload"]  # noqa: E731
        self.assertIsNone(qr())
        self.allow()
        self.assertTrue(qr().startswith("TX1:"))
