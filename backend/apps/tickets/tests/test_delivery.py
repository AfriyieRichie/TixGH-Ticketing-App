import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.messaging import SMSError
from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.notifications.models import Delivery
from apps.notifications.services import send_due_reminders
from apps.orders.models import Order, Ticket, TicketStatus
from apps.organizations.models import Membership, Organization, PayoutAccount, Role
from apps.tickets.models import TicketTransfer
from apps.tickets.signing import parse_payload, qr_payload

User = get_user_model()


class DeliveryBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.sms = []
        p = patch("apps.notifications.services.send_sms", side_effect=lambda to, m: self.sms.append((to, m)))
        p.start()
        self.addCleanup(p.stop)
        self.org = Organization.objects.create(name="Accra Live")
        PayoutAccount.objects.create(organization=self.org, method="mobile_money", mobile_money_provider="mtn",
                                     account_number="0241234567", account_name="A", is_default=True)
        venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra",
                                     directions="Enter by Gate 2")
        now = timezone.now()
        self.event = Event.objects.create(
            organization=self.org, title="Afrobeats Night", venue=venue, status=EventStatus.PUBLISHED,
            start_at=now + timedelta(days=5), end_at=now + timedelta(days=5, hours=5),
        )
        self.tt = TicketType.objects.create(event=self.event, name="Regular", price=Decimal("100"), quantity=50)

    def buy(self, qty=2, buyer=None, user=None):
        """Checkout + pay on the simulated gateway, running on_commit hooks (delivery)."""
        if user:
            self.client.force_authenticate(user)
        buyer = buyer or {"full_name": "Ama Mensah", "phone": "0241112222", "email": "ama@example.com"}
        with self.captureOnCommitCallbacks(execute=True):
            data = self.client.post("/api/v1/checkout/", {
                "event": self.event.slug, "items": [{"ticket_type": self.tt.pk, "quantity": qty}], "buyer": buyer,
            }, format="json").data
            url = data["payment"]["authorization_url"].replace("http://127.0.0.1:8000", "")
            self.client.post(url, {"outcome": "success"})
        self.client.force_authenticate(None)
        return Order.objects.get(reference=data["reference"])


class SigningTests(DeliveryBase):
    def test_qr_signature(self):
        order = self.buy(1)
        t = order.tickets.get()
        payload = qr_payload(t)
        self.assertTrue(payload.startswith(f"TX1:{t.code}:"))
        self.assertEqual(parse_payload(payload, self.event.pk), t.code)
        self.assertIsNone(parse_payload(payload, self.event.pk + 1))  # other event's key
        forged = f"TX1:{t.code[:-1]}X:{payload.split(':')[2]}"
        self.assertIsNone(parse_payload(forged, self.event.pk))
        self.assertEqual(parse_payload(t.code.lower(), self.event.pk), t.code)  # typed in by hand


class ConfirmationTests(DeliveryBase):
    def test_sms_and_email_with_pdf(self):
        order = self.buy(2)
        [(to, text)] = self.sms
        self.assertEqual(to, "+233241112222")
        self.assertIn("2 tickets for Afrobeats Night", text)
        self.assertIn(order.tickets_url, text)
        [email] = mail.outbox
        self.assertEqual(email.to, ["ama@example.com"])
        self.assertIn("Afrobeats Night", email.subject)
        name, content, mime = email.attachments[0]
        self.assertEqual(mime, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF"))
        html = email.alternatives[0][0]
        self.assertIn(order.tickets_url, html)
        self.assertEqual(Delivery.objects.filter(order=order, status="sent").count(), 2)

    def test_sms_failure_is_logged_not_fatal(self):
        with patch("apps.notifications.services.send_sms", side_effect=SMSError("provider down")):
            order = self.buy(1)
        self.assertEqual(order.status, "paid")
        self.assertTrue(Delivery.objects.filter(channel="sms", status="failed", error__contains="provider down").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_resend(self):
        order = self.buy(1)
        mail.outbox.clear()
        res = self.client.post(f"/api/v1/orders/{order.reference}/resend/?token={order.access_token}")
        self.assertEqual(res.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)

    def test_order_api_has_qr_and_links(self):
        order = self.buy(1)
        data = self.client.get(f"/api/v1/orders/{order.reference}/", {"token": order.access_token}).data
        self.assertTrue(data["tickets"][0]["qr_payload"].startswith("TX1:"))
        self.assertIn("wa.me", data["links"]["whatsapp_share"])
        self.assertEqual(data["links"]["tickets_page"], order.tickets_url)


class TicketPageTests(DeliveryBase):
    def test_order_page_and_pdf(self):
        order = self.buy(2)
        path = order.tickets_url.replace("http://127.0.0.1:8000", "")
        res = self.client.get(path)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "<svg", count=2)
        for t in order.tickets.all():
            self.assertContains(res, t.code)
        pdf = self.client.get(path + "pdf/")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_wrong_token_404(self):
        order = self.buy(1)
        self.assertEqual(self.client.get(f"/t/{order.reference}/wrong-token/").status_code, 404)
        t = order.tickets.get()
        self.assertEqual(self.client.get(f"/t/ticket/{t.code}/wrong/").status_code, 404)

    def test_checked_in_ticket_shows_no_qr(self):
        order = self.buy(1)
        order.tickets.update(status=TicketStatus.CHECKED_IN, checked_in_at=timezone.now())
        res = self.client.get(order.tickets_url.replace("http://127.0.0.1:8000", ""))
        self.assertNotContains(res, "<svg")
        self.assertContains(res, "Checked in")


class WalletAndTransferTests(DeliveryBase):
    def setUp(self):
        super().setUp()
        self.ama = User.objects.create_user(phone="0241112222", full_name="Ama Mensah", phone_verified=True)
        self.order = self.buy(2, user=self.ama)
        self.ticket = self.order.tickets.first()
        self.client.force_authenticate(self.ama)

    def test_wallet(self):
        res = self.client.get("/api/v1/tickets/")
        self.assertEqual(res.data["count"], 2)
        first = res.data["results"][0]
        self.assertTrue(first["qr_payload"].startswith("TX1:"))
        self.assertTrue(first["can_transfer"])
        self.assertEqual(self.client.get("/api/v1/tickets/", {"when": "past"}).data["count"], 0)
        res = self.client.patch(f"/api/v1/tickets/{self.ticket.code}/", {"attendee_name": "Kofi", "status": "void"})
        self.assertEqual(res.data["attendee_name"], "Kofi")
        self.assertEqual(res.data["status"], "valid")  # read-only
        pdf = self.client.get(f"/api/v1/tickets/{self.ticket.code}/pdf/")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_others_cannot_see_my_ticket(self):
        self.client.force_authenticate(User.objects.create_user(email="x@example.com"))
        self.assertEqual(self.client.get(f"/api/v1/tickets/{self.ticket.code}/").status_code, 404)

    def test_transfer_to_existing_user(self):
        kofi = User.objects.create_user(email="kofi@example.com", full_name="Kofi")
        old_code = self.ticket.code
        self.sms.clear()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(f"/api/v1/tickets/{old_code}/transfer/", {"to": "kofi@example.com", "name": "Kofi B"})
        self.assertEqual(res.status_code, 200, res.data)
        t = Ticket.objects.get(pk=self.ticket.pk)
        self.assertNotEqual(t.code, old_code)
        self.assertEqual(t.holder, kofi)
        self.assertEqual(TicketTransfer.objects.get().old_code, old_code)
        self.assertEqual(mail.outbox[-1].to, ["kofi@example.com"])
        self.assertIn("Ama Mensah sent you a ticket", mail.outbox[-1].subject)
        # Sender no longer has it; old QR is dead.
        self.assertEqual(self.client.get("/api/v1/tickets/").data["count"], 1)
        self.assertIsNone(parse_payload(f"TX1:{old_code}:x", self.event.pk))
        # The buyer's order page shows it as sent, without a QR.
        page = self.client.get(self.order.tickets_url.replace("http://127.0.0.1:8000", ""))
        self.assertContains(page, "Sent to Kofi B")
        self.assertContains(page, "<svg", count=1)
        # Recipient sees it in their wallet.
        self.client.force_authenticate(kofi)
        self.assertEqual(self.client.get("/api/v1/tickets/").data["results"][0]["code"], t.code)

    @patch("apps.accounts.otp.send_sms")
    def test_transfer_to_new_phone_then_claim_on_signup(self, otp_sms):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/v1/tickets/{self.ticket.code}/transfer/", {"to": "0207654321", "name": "Esi"})
        t = Ticket.objects.get(pk=self.ticket.pk)
        self.assertIsNone(t.holder)
        self.assertEqual(self.sms[-1][0], "+233207654321")
        self.assertIn(t.page_url, self.sms[-1][1])
        # Esi signs up with that number and finds the ticket in her wallet.
        self.client.force_authenticate(None)
        self.client.post("/api/v1/auth/otp/request/", {"identifier": "0207654321"})
        code = re.search(r"\b(\d{6})\b", otp_sms.call_args[0][1]).group(1)
        tokens = self.client.post("/api/v1/auth/otp/verify/", {"identifier": "0207654321", "code": code}).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual([x["code"] for x in self.client.get("/api/v1/tickets/").data["results"]], [t.code])

    def test_transfer_rules(self):
        url = f"/api/v1/tickets/{self.ticket.code}/transfer/"
        self.assertEqual(self.client.post(url, {"to": "0241112222", "name": "Me"}).status_code, 400)  # self
        self.event.allow_transfers = False
        self.event.save()
        self.assertIn("turned off", str(self.client.post(url, {"to": "0207654321", "name": "E"}).data))
        self.event.allow_transfers = True
        self.event.save()
        Ticket.objects.filter(pk=self.ticket.pk).update(status=TicketStatus.CHECKED_IN)
        self.assertIn("used or voided", str(self.client.post(url, {"to": "0207654321", "name": "E"}).data))


class EventLifecycleNoticeTests(DeliveryBase):
    def test_cancellation_notifies_buyers(self):
        self.buy(1)
        owner = User.objects.create_user(email="owner@example.com")
        Membership.objects.create(organization=self.org, user=owner, role=Role.OWNER)
        self.client.force_authenticate(owner)
        self.sms.clear()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/v1/organizations/{self.org.slug}/events/{self.event.slug}/cancel/",
                             {"reason": "Heavy rains"})
        self.assertIn("has been cancelled", self.sms[0][1])
        self.assertIn("Heavy rains", mail.outbox[0].body)

    def test_reminders_sent_once(self):
        order = self.buy(1)
        self.assertEqual(send_due_reminders(), 0)  # event is 5 days away
        Event.objects.filter(pk=self.event.pk).update(
            start_at=timezone.now() + timedelta(hours=20), end_at=timezone.now() + timedelta(hours=25)
        )
        self.sms.clear()
        self.assertEqual(send_due_reminders(), 1)
        self.assertIn("reminder", self.sms[0][1])
        self.assertIn("Enter by Gate 2", mail.outbox[-1].alternatives[0][0])
        self.assertEqual(send_due_reminders(), 0)
        order.refresh_from_db()
        self.assertIsNotNone(order.reminder_sent_at)
