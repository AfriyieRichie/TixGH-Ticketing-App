"""
Payment gateway layer. Business code only talks to `get_gateway()`, so the
provider can be swapped (Paystack today; Hubtel/Flutterwave later) via the
PAYMENT_GATEWAY setting.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    pass


@dataclass
class InitResult:
    authorization_url: str
    access_code: str = ""


@dataclass
class VerifyResult:
    status: str  # "success" | "failed" | "abandoned" | "pending"
    amount: Decimal | None = None
    currency: str = "GHS"
    channel: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RefundResult:
    status: str  # "processing" | "processed" | "failed"
    reference: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Split:
    """Send `organizer_amount` to the organizer's subaccount; the rest stays with the platform."""

    subaccount_code: str
    platform_amount: Decimal


def to_minor(amount: Decimal) -> int:
    """GHS -> pesewas."""
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def from_minor(value) -> Decimal:
    return (Decimal(value) / 100).quantize(Decimal("0.01"))


class BaseGateway:
    name = "base"

    def initialize(self, payment, email: str, split: Split | None) -> InitResult:
        raise NotImplementedError

    def verify(self, payment) -> VerifyResult:
        raise NotImplementedError

    def webhook_reference(self, request) -> str | None:
        """Validate a webhook and return the payment reference it confirms (or None)."""
        raise NotImplementedError

    def ensure_subaccount(self, payout_account) -> str:
        """Return the gateway subaccount code for an organizer payout account ('' if unavailable)."""
        raise NotImplementedError

    def list_banks(self) -> list[dict]:
        """Ghana banks organizers can be paid into: [{"name", "code"}]."""
        raise NotImplementedError

    def refund(self, payment, amount: Decimal, note: str = "") -> RefundResult:
        """Return `amount` of a successful payment to the buyer's original MoMo/card."""
        raise NotImplementedError

    def refund_status(self, reference: str) -> str:
        raise NotImplementedError


class SimulatedGateway(BaseGateway):
    """
    Development stand-in: no real money moves. The "checkout page" is served by
    this backend at /api/v1/payments/simulated/<reference>/ where you click
    Pay or Fail. Verify returns whatever outcome was chosen there.
    """

    name = "simulated"

    def initialize(self, payment, email, split):
        path = reverse("payment-simulated", kwargs={"reference": payment.reference})
        return InitResult(authorization_url=f"{settings.BACKEND_URL}{path}", access_code="SIM")

    def verify(self, payment):
        outcome = payment.gateway_response.get("simulated_outcome")
        if outcome == "success":
            return VerifyResult("success", amount=payment.amount, channel=payment.gateway_response.get(
                "simulated_channel", "mobile_money"), raw=payment.gateway_response)
        if outcome == "failed":
            return VerifyResult("failed", raw=payment.gateway_response)
        return VerifyResult("pending")

    def webhook_reference(self, request):
        return None

    def ensure_subaccount(self, payout_account):
        return f"SIM_{payout_account.pk}"

    def refund(self, payment, amount, note=""):
        return RefundResult("processed", reference=f"SIMREF-{payment.reference}")

    def refund_status(self, reference):
        return "processed"

    def list_banks(self):
        return [
            {"name": "Absa Bank Ghana Ltd", "code": "030100"}, {"name": "Access Bank", "code": "280100"},
            {"name": "Ecobank Ghana", "code": "130100"}, {"name": "Fidelity Bank", "code": "240100"},
            {"name": "GCB Bank", "code": "040100"}, {"name": "Stanbic Bank", "code": "190100"},
        ]


class PaystackGateway(BaseGateway):
    """https://paystack.com/docs/api/  (amounts are sent in pesewas)"""

    name = "paystack"
    base_url = "https://api.paystack.co"
    timeout = 20
    # Paystack's settlement codes for Ghana mobile money networks.
    MOMO_SETTLEMENT_CODES = {"mtn": "MTN", "telecel": "VOD", "airteltigo": "ATL"}

    def __init__(self):
        if not settings.PAYSTACK_SECRET_KEY:
            raise GatewayError("PAYSTACK_SECRET_KEY is not set.")
        self.secret = settings.PAYSTACK_SECRET_KEY

    def _request(self, method, path, **kwargs) -> dict:
        try:
            resp = requests.request(
                method, f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.secret}"}, timeout=self.timeout, **kwargs,
            )
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.exception("Paystack request failed: %s %s", method, path)
            raise GatewayError("Could not reach Paystack.") from exc
        if resp.status_code >= 400 or not body.get("status"):
            raise GatewayError(body.get("message") or f"Paystack error {resp.status_code}")
        return body["data"]

    def initialize(self, payment, email, split):
        payload = {
            "email": email,
            "amount": to_minor(payment.amount),
            "currency": payment.currency,
            "reference": payment.reference,
            "callback_url": f"{settings.PAYMENT_CALLBACK_URL}?reference={payment.order.reference}",
            "channels": ["mobile_money", "card"],
            "metadata": {
                "order_reference": payment.order.reference,
                "event": payment.order.event.title,
            },
        }
        if split and split.subaccount_code:
            payload.update(
                subaccount=split.subaccount_code,
                transaction_charge=to_minor(split.platform_amount),
                bearer="account",  # platform pays Paystack's charge out of its share
            )
        data = self._request("POST", "/transaction/initialize", json=payload)
        return InitResult(authorization_url=data["authorization_url"], access_code=data.get("access_code", ""))

    def verify(self, payment):
        data = self._request("GET", f"/transaction/verify/{payment.reference}")
        status = {"success": "success", "failed": "failed", "abandoned": "abandoned"}.get(
            data.get("status"), "pending"
        )
        return VerifyResult(
            status=status, amount=from_minor(data.get("amount", 0)), currency=data.get("currency", "GHS"),
            channel=data.get("channel", ""), raw=data,
        )

    def webhook_reference(self, request):
        signature = request.headers.get("x-paystack-signature", "")
        expected = hmac.new(self.secret.encode(), request.body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Rejected Paystack webhook with bad signature")
            return None
        try:
            payload = json.loads(request.body)
        except ValueError:
            return None
        if payload.get("event") != "charge.success":
            return None
        return (payload.get("data") or {}).get("reference")

    def ensure_subaccount(self, payout_account):
        if payout_account.gateway_subaccount_code:
            return payout_account.gateway_subaccount_code
        if payout_account.method == "mobile_money":
            bank = self.MOMO_SETTLEMENT_CODES.get(payout_account.mobile_money_provider, "")
        else:
            bank = payout_account.bank_code
        data = self._request(
            "POST", "/subaccount",
            json={
                "business_name": payout_account.organization.name[:100],
                "settlement_bank": bank,
                "account_number": payout_account.account_number,
                "percentage_charge": 0,  # overridden per transaction by transaction_charge
            },
        )
        payout_account.gateway_subaccount_code = data["subaccount_code"]
        payout_account.is_verified = True
        payout_account.save(update_fields=["gateway_subaccount_code", "is_verified", "updated_at"])
        return payout_account.gateway_subaccount_code


    REFUND_STATUS = {"pending": "processing", "processing": "processing", "processed": "processed",
                     "failed": "failed", "reversed": "processed", "needs-attention": "failed"}

    def refund(self, payment, amount, note=""):
        data = self._request("POST", "/refund", json={
            "transaction": payment.reference, "amount": to_minor(amount), "merchant_note": note[:200],
        })
        return RefundResult(self.REFUND_STATUS.get(str(data.get("status", "")).lower(), "processing"),
                            reference=str(data.get("id", "")), raw=data)

    def refund_status(self, reference):
        data = self._request("GET", f"/refund/{reference}")
        return self.REFUND_STATUS.get(str(data.get("status", "")).lower(), "processing")

    def list_banks(self):
        data = self._request("GET", "/bank", params={"currency": "GHS", "type": "ghipss"})
        return [{"name": b["name"], "code": b["code"]} for b in data if b.get("active", True)]


_GATEWAYS = {"simulated": SimulatedGateway, "paystack": PaystackGateway}


def get_gateway(name: str | None = None) -> BaseGateway:
    name = name or settings.PAYMENT_GATEWAY
    try:
        return _GATEWAYS[name]()
    except KeyError as exc:
        raise GatewayError(f"Unknown payment gateway '{name}'") from exc
