"""
Ticket price breakdown. Checkout (Phase 3) uses the same function, so what a
buyer sees on the event page always matches what they are charged.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal

from apps.core.models import FeeBearer, PlatformSettings


@dataclass(frozen=True)
class PriceBreakdown:
    price: Decimal  # face value set by the organizer (after any discount)
    fee: Decimal  # platform booking fee for this ticket
    buyer_pays: Decimal
    organizer_receives: Decimal
    fee_bearer: str

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}


def price_breakdown(event, price: Decimal, platform: PlatformSettings | None = None) -> PriceBreakdown:
    platform = platform or PlatformSettings.load()
    org = event.organization
    fee = platform.ticket_fee(price, percent=org.fee_percent_override, flat=org.fee_flat_override)
    bearer = event.effective_fee_bearer
    if bearer == FeeBearer.BUYER:
        buyer_pays, organizer_receives = price + fee, price
    else:
        buyer_pays, organizer_receives = price, max(price - fee, Decimal("0.00"))
    return PriceBreakdown(price, fee, buyer_pays, organizer_receives, bearer)
