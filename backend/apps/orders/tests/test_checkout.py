import hashlib
import hmac
import json
import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.events.models import Event, EventStatus, PromoCode, TicketType, Venue
from apps.orders.models import Order, OrderStatus, Ticket
from apps.orders.services import expire_stale_orders
from apps.organizations.models import Organization, PayoutAccount
from apps.payments.gateways import PaystackGateway
from apps.payments.models import Payment

User = get_user_model()


class CheckoutBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Accra Live")
        PayoutAccount.objects.create(
            organization=self.org, method="mobile_money", mobile_money_provider="mtn",
            account_number="0241234567", account_name="Accra Live", is_default=True,
        )
        venue = Venue.objects.create(organization=self.org, name="AICC", city="Accra", region="greater_accra")
        now = timezone.now()
        self.event = Event.objects.create(
            organization=self.org, title="Afrobeats Night", venue=venue, status=EventStatus.PUBLISHED,
            start_at=now + timedelta(days=5), end_at=now + timedelta(days=5, hours=5),
        )
        self.regular = TicketType.objects.create(event=self.event, name="Regular", price=Decimal("100"), quantity=50)
        self.free = TicketType.objects.create(event=self.event, name="Free", price=Decimal("0"), quantity=50)
        self.buyer = {"full_name": "Ama Mensah", "phone": "0241112222"}

    def checkout(self, items, **extra):
        payload = {"event": self.event.slug, "items": items, "buyer": self.buyer, **extra}
        return self.client.post("/api/v1/checkout/", payload, format="json")

    def pay(self, order_data, outcome="success"):
        """Click a button on the simulated gateway page."""
        url = order_data["payment"]["authorization_url"].replace("http://127.0.0.1:8000", "")
        return self.client.post(url, {"outcome": outcome, "channel": "mobile_money"})

    def get_order(self, data):
        return self.client.get(f"/api/v1/orders/{data['reference']}/", {"token": data["access_token"]}).data


class PaidCheckoutTests(CheckoutBase):
    def test_full_paid_flow(self):
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}])
        self.assertEqual(res.status_code, 201, res.data)
        data = res.data
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["total"], "212.00")  # 2 x (100 + 5% + 1)
        self.assertEqual(data["fee_total"], "12.00")
        self.assertGreater(data["seconds_left"], 500)
        self.assertIn("/payments/simulated/", data["payment"]["authorization_url"])
        self.assertEqual(data["tickets"], [])

        order = Order.objects.get()
        self.assertEqual((order.organizer_amount, order.platform_amount), (Decimal("200"), Decimal("12")))
        self.assertEqual(order.buyer_phone, "+233241112222")

        page = self.pay(data)
        self.assertContains(page, "Payment successful")
        order = self.get_order(data)
        self.assertEqual(order["status"], "paid")
        self.assertEqual(len(order["tickets"]), 2)
        self.assertTrue(all(re.fullmatch(r"[2-9A-Z]{10}", t["code"]) for t in order["tickets"]))
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.quantity_sold, 2)
        self.assertEqual(Payment.objects.get().channel, "mobile_money")

    def test_verify_is_idempotent(self):
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 3}]).data
        self.pay(data)
        for _ in range(3):
            res = self.client.post(f"/api/v1/orders/{data['reference']}/verify/?token={data['access_token']}")
            self.assertEqual(res.data["status"], "paid")
        self.assertEqual(Ticket.objects.count(), 3)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.quantity_sold, 3)

    def test_declined_then_retry(self):
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}]).data
        self.assertContains(self.pay(data, "failed"), "declined")
        self.assertEqual(self.get_order(data)["status"], "pending")
        res = self.client.post(f"/api/v1/orders/{data['reference']}/retry-payment/?token={data['access_token']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Payment.objects.count(), 2)
        self.pay(res.data)
        self.assertEqual(self.get_order(data)["status"], "paid")

    def test_organizer_absorbs_fees(self):
        self.event.fee_bearer = "organizer"
        self.event.save()
        self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}])
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("200"))
        self.assertEqual(order.organizer_amount, Decimal("188"))
        self.assertEqual(order.platform_amount, Decimal("12"))

    def test_amount_mismatch_flags_for_review(self):
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}]).data
        payment = Payment.objects.get()
        payment.gateway_response = {"simulated_outcome": "success"}
        payment.save()
        with patch("apps.payments.gateways.SimulatedGateway.verify") as verify:
            from apps.payments.gateways import VerifyResult

            verify.return_value = VerifyResult("success", amount=Decimal("1.00"))
            self.client.post(f"/api/v1/orders/{data['reference']}/verify/?token={data['access_token']}")
        order = Order.objects.get()
        self.assertEqual(order.status, OrderStatus.NEEDS_REVIEW)
        self.assertEqual(Ticket.objects.count(), 0)


class FreeAndValidationTests(CheckoutBase):
    def test_free_order_completes_immediately(self):
        res = self.checkout([{"ticket_type": self.free.pk, "quantity": 2}])
        self.assertEqual(res.data["status"], "paid")
        self.assertEqual(len(res.data["tickets"]), 2)
        self.assertIsNone(res.data["payment"])

    def test_buyer_contact_required(self):
        self.buyer = {"full_name": "No Contact"}
        self.assertEqual(self.checkout([{"ticket_type": self.free.pk, "quantity": 1}]).status_code, 400)
        self.buyer = {"phone": "0241112222"}
        self.assertEqual(self.checkout([{"ticket_type": self.free.pk, "quantity": 1}]).status_code, 400)

    def test_signed_in_user_details_used(self):
        user = User.objects.create_user(phone="0559998888", full_name="Kofi Owusu")
        self.client.force_authenticate(user)
        self.buyer = {}
        res = self.checkout([{"ticket_type": self.free.pk, "quantity": 1}])
        self.assertEqual(res.data["buyer_name"], "Kofi Owusu")
        self.assertEqual(Ticket.objects.get().holder, user)
        self.assertEqual(self.client.get("/api/v1/orders/").data["count"], 1)

    def test_rules(self):
        other_event = Event.objects.create(
            organization=self.org, title="Other", status=EventStatus.PUBLISHED,
            start_at=timezone.now() + timedelta(days=1), end_at=timezone.now() + timedelta(days=2),
        )
        foreign = TicketType.objects.create(event=other_event, name="X", price=0, quantity=5)
        self.regular.max_per_order = 4
        self.regular.save()
        cases = [
            ([{"ticket_type": foreign.pk, "quantity": 1}], "not part of this event"),
            ([{"ticket_type": self.regular.pk, "quantity": 5}], "between 1 and 4"),
            ([{"ticket_type": self.regular.pk, "quantity": 0}], "at least one"),
            ([{"ticket_type": self.free.pk, "quantity": 11}], "at most 10"),
        ]
        for items, msg in cases:
            res = self.checkout(items)
            self.assertEqual(res.status_code, 400, items)
            self.assertIn(msg, str(res.data))

    def test_sales_window(self):
        self.regular.sales_start_at = timezone.now() + timedelta(days=1)
        self.regular.save()
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}])
        self.assertIn("not on sale yet", str(res.data))

    def test_unpublished_or_cancelled_event(self):
        for st in (EventStatus.DRAFT, EventStatus.CANCELLED):
            self.event.status = st
            self.event.save()
            self.assertEqual(self.checkout([{"ticket_type": self.free.pk, "quantity": 1}]).status_code, 400)


class StockAndHoldTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.regular.quantity = 3
        self.regular.save()

    def test_holds_block_other_buyers_until_expiry(self):
        first = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}]).data
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}])
        self.assertIn("Only 1", str(res.data))
        Order.objects.filter(reference=first["reference"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}]).status_code, 201)

    def test_sold_out(self):
        self.pay(self.checkout([{"ticket_type": self.regular.pk, "quantity": 3}]).data)
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}])
        self.assertIn("sold out", str(res.data))

    def test_late_payment_honoured_if_stock_remains(self):
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}]).data
        Order.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(expire_stale_orders(), 1)
        self.pay(data)
        self.assertEqual(Order.objects.get().status, OrderStatus.PAID)

    def test_late_payment_flagged_if_resold(self):
        late = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}]).data
        Order.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        newer = self.checkout([{"ticket_type": self.regular.pk, "quantity": 3}]).data
        self.pay(newer)
        self.pay(late)
        late_order = Order.objects.get(reference=late["reference"])
        self.assertEqual(late_order.status, OrderStatus.NEEDS_REVIEW)
        self.assertIn("Refund", late_order.review_note)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.quantity_sold, 3)  # never oversold

    def test_retry_after_expiry_refused(self):
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}]).data
        Order.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        res = self.client.post(f"/api/v1/orders/{data['reference']}/retry-payment/?token={data['access_token']}")
        self.assertEqual(res.status_code, 400)


class PromoCheckoutTests(CheckoutBase):
    def test_discount_and_usage(self):
        promo = PromoCode.objects.create(event=self.event, code="AFRO20", discount_type="percent", amount=20, max_uses=1)
        data = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}], promo_code="afro20").data
        self.assertEqual(data["discount_total"], "40.00")
        self.assertEqual(data["total"], "170.00")  # 2 x (80 + 4 + 1)
        # The pending order counts against max_uses.
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}], promo_code="AFRO20")
        self.assertIn("fully used", str(res.data))
        self.pay(data)
        promo.refresh_from_db()
        self.assertEqual(promo.times_used, 1)

    def test_hidden_ticket_needs_access_code(self):
        vip = TicketType.objects.create(event=self.event, name="VIP", price=500, quantity=5, visibility="hidden")
        res = self.checkout([{"ticket_type": vip.pk, "quantity": 1}])
        self.assertIn("requires an access code", str(res.data))
        code = PromoCode.objects.create(event=self.event, code="VIPLIST", discount_type="none")
        code.ticket_types.add(vip)
        self.assertEqual(self.checkout([{"ticket_type": vip.pk, "quantity": 1}], promo_code="VIPLIST").status_code, 201)

    def test_code_must_apply_to_selection(self):
        vip = TicketType.objects.create(event=self.event, name="VIP", price=500, quantity=5)
        code = PromoCode.objects.create(event=self.event, code="VIPONLY", amount=10)
        code.ticket_types.add(vip)
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}], promo_code="VIPONLY")
        self.assertIn("doesn't apply", str(res.data))

    def test_100_percent_code_makes_order_free(self):
        PromoCode.objects.create(event=self.event, code="COMP", amount=100)
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}], promo_code="COMP")
        self.assertEqual(res.data["status"], "paid")
        self.assertEqual(res.data["total"], "0.00")


class OrderAccessTests(CheckoutBase):
    def test_guest_needs_token(self):
        data = self.checkout([{"ticket_type": self.free.pk, "quantity": 1}]).data
        url = f"/api/v1/orders/{data['reference']}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url, {"token": "wrong"}).status_code, 404)
        self.assertEqual(self.client.get(url, {"token": data["access_token"]}).status_code, 200)
        self.client.force_authenticate(User.objects.create_user(email="snoop@example.com"))
        self.assertEqual(self.client.get(url).status_code, 404)

    @patch("apps.accounts.otp.send_sms")
    def test_guest_orders_claimed_on_login(self, send_sms):
        self.checkout([{"ticket_type": self.free.pk, "quantity": 2}])
        self.client.post("/api/v1/auth/otp/request/", {"identifier": "0241112222"})
        code = re.search(r"\b(\d{6})\b", send_sms.call_args[0][1]).group(1)
        res = self.client.post("/api/v1/auth/otp/verify/", {"identifier": "0241112222", "code": code})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        orders = self.client.get("/api/v1/orders/").data
        self.assertEqual(orders["count"], 1)
        self.assertEqual(len(orders["results"][0]["tickets"]), 2)
        self.assertEqual(Ticket.objects.filter(holder__phone="+233241112222").count(), 2)


@override_settings(PAYMENT_GATEWAY="paystack", PAYSTACK_SECRET_KEY="sk_test_abc")
class PaystackGatewayTests(CheckoutBase):
    def _resp(self, data, status=200):
        r = MagicMock(status_code=status)
        r.json.return_value = {"status": status < 400, "message": "ok", "data": data}
        return r

    @patch("apps.payments.gateways.requests.request")
    def test_initialize_sends_split_in_pesewas(self, req):
        req.side_effect = [
            self._resp({"subaccount_code": "ACCT_123"}),
            self._resp({"authorization_url": "https://checkout.paystack.com/x", "access_code": "abc"}),
        ]
        res = self.checkout([{"ticket_type": self.regular.pk, "quantity": 2}])
        self.assertEqual(res.data["payment"]["authorization_url"], "https://checkout.paystack.com/x")
        sub_call, init_call = req.call_args_list
        self.assertEqual(sub_call.kwargs["json"]["settlement_bank"], "MTN")
        body = init_call.kwargs["json"]
        self.assertEqual(body["amount"], 21200)
        self.assertEqual(body["subaccount"], "ACCT_123")
        self.assertEqual(body["transaction_charge"], 1200)
        self.assertEqual(body["bearer"], "account")
        self.assertEqual(body["email"], "233241112222@customers.tixgh.com")
        self.assertEqual(PayoutAccount.objects.get().gateway_subaccount_code, "ACCT_123")

    @patch("apps.payments.gateways.requests.request")
    def test_webhook_with_valid_signature_fulfils(self, req):
        req.side_effect = [
            self._resp({"subaccount_code": "ACCT_123"}),
            self._resp({"authorization_url": "https://checkout.paystack.com/x"}),
        ]
        self.checkout([{"ticket_type": self.regular.pk, "quantity": 1}])
        payment = Payment.objects.get()
        body = json.dumps({"event": "charge.success", "data": {"reference": payment.reference}}).encode()

        bad = self.client.post("/api/v1/payments/webhook/paystack/", body, content_type="application/json",
                               HTTP_X_PAYSTACK_SIGNATURE="nope")
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(Order.objects.get().status, "pending")

        req.side_effect = [self._resp({"status": "success", "amount": 10600, "currency": "GHS", "channel": "mobile_money"})]
        sig = hmac.new(b"sk_test_abc", body, hashlib.sha512).hexdigest()
        ok = self.client.post("/api/v1/payments/webhook/paystack/", body, content_type="application/json",
                              HTTP_X_PAYSTACK_SIGNATURE=sig)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(Order.objects.get().status, "paid")
        self.assertEqual(Ticket.objects.count(), 1)

    def test_simulated_page_disabled_in_paystack_mode(self):
        self.assertEqual(self.client.get("/api/v1/payments/simulated/PAY-X/").status_code, 404)


class BankListTests(APITestCase):
    def test_simulated_bank_list(self):
        cache.clear()
        res = self.client.get("/api/v1/payments/banks/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("GCB Bank", [b["name"] for b in res.data])
