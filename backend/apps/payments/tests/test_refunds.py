from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Event, EventStatus, TicketType, Venue
from apps.orders.models import Order, OrderStatus, Ticket, TicketStatus
from apps.orders.services import create_order, fulfil_order
from apps.organizations.models import Membership, Organization, PayoutAccount, Role
from apps.payments.gateways import GatewayError
from apps.payments.models import Payment, PaymentStatus, Refund, RefundStatus
from apps.payments.refunds import check_refunds

User = get_user_model()


class RefundBase(APITestCase):
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
            start_at=now + timedelta(days=10), end_at=now + timedelta(days=10, hours=5), refund_policy="7_days",
        )
        self.tt = TicketType.objects.create(event=self.event, name="Regular", price=Decimal("100"), quantity=10)
        self.base = f"/api/v1/organizations/{self.org.slug}/events/{self.event.slug}/"
        self.client.force_authenticate(self.owner)

    def paid_order(self, qty=2):
        """GHS 100 tickets, buyer pays the 5% + GHS 1 fee: 106 each."""
        o = create_order(event=self.event, items=[{"ticket_type": self.tt.pk, "quantity": qty}],
                         buyer={"full_name": "Ama", "phone": "0241112222", "email": "ama@example.com"})
        Payment.objects.create(order=o, gateway="simulated", amount=o.total, status=PaymentStatus.SUCCESS,
                               amount_paid=o.total, paid_at=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            return fulfil_order(o, amount_paid=o.total)

    def refund(self, order, **body):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f"{self.base}orders/{order.reference}/refund/", body, format="json")


class OrganizerRefundTests(RefundBase):
    def test_full_order_refund_price_only(self):
        order = self.paid_order(2)
        mail.outbox.clear()
        res = self.refund(order, reason="Customer asked")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["amount"], res.data["organizer_amount"], res.data["status"]), ("200.00", "200.00", "pending"))
        r = Refund.objects.get()
        self.assertEqual(r.status, RefundStatus.PROCESSED)  # simulated gateway, processed in background
        order.refresh_from_db()
        self.assertEqual((order.status, order.refunded_amount), (OrderStatus.REFUNDED, Decimal("200")))
        self.assertEqual(Ticket.objects.filter(order=order, status=TicketStatus.VOID).count(), 2)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.quantity_sold, 0)  # seats back on sale
        self.assertIn("Refund: Afrobeats Night", mail.outbox[-1].subject)
        self.assertIn("booking fee is not refundable", mail.outbox[-1].body)

    def test_partial_refund_and_dashboard_totals(self):
        order = self.paid_order(2)
        code = order.tickets.first().code
        self.assertEqual(self.refund(order, tickets=[code]).data["amount"], "100.00")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        stats = self.client.get(f"{self.base}stats/").data
        self.assertEqual((stats["organizer_earnings"], stats["refunded"], stats["tickets_sold"]), ("100.00", "100.00", 1))
        self.assertEqual(self.refund(order, tickets=[code]).status_code, 400)  # already refunded
        self.assertEqual(self.client.get(f"{self.base}refunds/").data[0]["tickets"], [code])

    def test_roles(self):
        order = self.paid_order(1)
        mk = User.objects.create_user(email="mk@example.com")
        Membership.objects.create(organization=self.org, user=mk, role=Role.MARKETING)
        self.client.force_authenticate(mk)
        self.assertEqual(self.refund(order).status_code, 403)

    def test_free_order_refund_needs_no_gateway(self):
        free = TicketType.objects.create(event=self.event, name="Free", price=0, quantity=5)
        o = create_order(event=self.event, items=[{"ticket_type": free.pk, "quantity": 1}], buyer={"full_name": "K", "phone": "0201111111"})
        res = self.refund(o)
        self.assertEqual((res.data["amount"], res.data["status"]), ("0.00", "processed"))


class CancellationRefundTests(RefundBase):
    def test_cancel_refunds_everything_including_fees(self):
        a = self.paid_order(2)
        b = self.paid_order(1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{self.base}cancel/", {"reason": "Venue flooded"})
        refunds = {r.order_id: r for r in Refund.objects.all()}
        self.assertEqual(refunds[a.pk].amount, Decimal("212.00"))
        self.assertEqual((refunds[b.pk].amount, refunds[b.pk].platform_amount, refunds[b.pk].organizer_amount),
                         (Decimal("106.00"), Decimal("6.00"), Decimal("100.00")))
        self.assertTrue(all(r.status == RefundStatus.PROCESSED for r in refunds.values()))
        self.assertEqual(Order.objects.filter(status=OrderStatus.REFUNDED).count(), 2)


class BuyerRefundTests(RefundBase):
    def url(self, order):
        return f"/api/v1/orders/{order.reference}/refund/?token={order.access_token}"

    def test_within_policy(self):
        order = self.paid_order(2)
        self.client.force_authenticate(None)
        quote = self.client.get(self.url(order)).data
        self.assertTrue(quote["eligible"])
        self.assertEqual(quote["amount"], "200.00")
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(self.url(order))
        self.assertEqual((res.status_code, res.data["amount"]), (201, "200.00"))

    def test_outside_policy_or_no_refunds(self):
        order = self.paid_order(1)
        Event.objects.filter(pk=self.event.pk).update(start_at=timezone.now() + timedelta(days=3))
        self.client.force_authenticate(None)
        self.assertIn("closed", self.client.get(self.url(order)).data["reason"])
        Event.objects.filter(pk=self.event.pk).update(refund_policy="no_refunds")
        self.assertEqual(self.client.post(self.url(order)).status_code, 400)

    def test_used_and_transferred_tickets_excluded(self):
        order = self.paid_order(3)
        t1, t2, _ = order.tickets.all()
        Ticket.objects.filter(pk=t1.pk).update(status=TicketStatus.CHECKED_IN)
        Ticket.objects.filter(pk=t2.pk).update(transferred_at=timezone.now())
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url(order)).data["amount"], "100.00")


@override_settings(PAYMENT_GATEWAY="paystack", PAYSTACK_SECRET_KEY="sk_test_x")
class PaystackRefundTests(RefundBase):
    def resp(self, data, status=200):
        r = MagicMock(status_code=status)
        r.json.return_value = {"status": status < 400, "message": "ok" if status < 400 else "bad", "data": data}
        return r

    def paid_paystack_order(self):
        order = self.paid_order(1)
        order.payments.update(gateway="paystack")
        return order

    @patch("apps.payments.gateways.requests.request")
    def test_refund_sent_in_pesewas_then_polled(self, req):
        order = self.paid_paystack_order()
        req.return_value = self.resp({"id": 777, "status": "pending"})
        self.refund(order)
        r = Refund.objects.get()
        self.assertEqual((r.status, r.gateway_reference), (RefundStatus.PROCESSING, "777"))
        body = req.call_args.kwargs["json"]
        self.assertEqual((body["amount"], body["transaction"]), (10000, order.payments.first().reference))
        req.return_value = self.resp({"id": 777, "status": "processed"})
        check_refunds()
        r.refresh_from_db()
        self.assertEqual(r.status, RefundStatus.PROCESSED)

    @patch("apps.payments.gateways.PaystackGateway.refund", side_effect=GatewayError("Paystack down"))
    def test_retries_then_fails(self, _):
        order = self.paid_paystack_order()
        self.refund(order)
        check_refunds()
        check_refunds()
        r = Refund.objects.get()
        self.assertEqual((r.status, r.attempts), (RefundStatus.FAILED, 3))
        self.assertIn("Paystack down", r.error)
