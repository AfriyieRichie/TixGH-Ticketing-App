"""
Create a demo organizer with sample events across Ghana.

    python manage.py seed_demo          # safe to run more than once
    python manage.py seed_demo --reset  # delete demo data first
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.events.models import Category, Event, EventStatus, PromoCode, TicketType, Venue
from apps.organizations.models import Membership, Organization, PayoutAccount, Role, VerificationStatus

DEMO_EMAIL = "demo.organizer@tixgh.local"
DEMO_ORG = "TixGH Demo Promotions"

VENUES = [
    ("Accra International Conference Centre", "Castle Road, Ridge", "Accra", "greater_accra"),
    ("Baba Yara Sports Stadium", "Amakom", "Kumasi", "ashanti"),
    ("Takoradi Harbour View Hotel", "Harbour Road", "Takoradi", "western"),
    ("Tamale Jubilee Park", "Jubilee Park", "Tamale", "northern"),
    ("Labadi Beach", "La", "Accra", "greater_accra"),
]

# title, category, venue index, days from now, start hour, hours long, summary, tickets[(name, price, qty)]
EVENTS = [
    ("Afrobeats Live in Accra", "music", 0, 9, 19, 5, "A night of Ghana's biggest Afrobeats and highlife acts.",
     [("Early Bird", "150", 200), ("Regular", "250", 800), ("VIP", "600", 150), ("VIP Table for 8", "4500", 20)]),
    ("Kumasi Gospel Praise Night", "church-gospel", 1, 16, 18, 5, "An evening of worship with choirs from across Ashanti.",
     [("Free Entry", "0", 3000)]),
    ("Ghana Tech Summit", "tech", 0, 30, 9, 8, "Founders, engineers and investors building Africa's digital future.",
     [("Student", "100", 300), ("Professional", "450", 500), ("Founder Pass", "1200", 80)]),
    ("Takoradi Comedy Jam", "comedy", 2, 12, 20, 3, "Ghana's funniest comedians, live in the Oil City.",
     [("Regular", "120", 400), ("VIP", "300", 80)]),
    ("Tamale Fire Festival Concert", "festivals", 3, 22, 17, 6, "Celebrating northern culture with music and dance.",
     [("Regular", "50", 2000)]),
    ("Labadi Beach Day Party", "nightlife", 4, 5, 12, 10, "Sun, sand and DJs all day at Labadi.",
     [("General", "80", 1500), ("Cabana for 6", "1800", 15)]),
]


class Command(BaseCommand):
    help = "Create demo organizer and events (for development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")

    @transaction.atomic
    def handle(self, *args, reset=False, **opts):
        User = get_user_model()
        if reset:
            org = Organization.objects.filter(name=DEMO_ORG).first()
            if org:
                Event.objects.filter(organization=org).delete()
                org.delete()
            self.stdout.write("Removed old demo data.")

        user, _ = User.objects.get_or_create(email=DEMO_EMAIL, defaults={"full_name": "Demo Organizer"})
        org, created = Organization.objects.get_or_create(
            name=DEMO_ORG,
            defaults=dict(
                created_by=user, description="Demo organizer with sample events.", region="greater_accra",
                city="Accra", phone="+233241234567", verification_status=VerificationStatus.VERIFIED,
            ),
        )
        if not created and org.events.exists():
            self.stdout.write(self.style.WARNING("Demo data already exists (use --reset to recreate)."))
            return
        Membership.objects.get_or_create(organization=org, user=user, defaults={"role": Role.OWNER})
        PayoutAccount.objects.get_or_create(
            organization=org, account_number="0241234567",
            defaults=dict(method="mobile_money", mobile_money_provider="mtn",
                          account_name="TixGH Demo", is_default=True),
        )
        venues = [
            Venue.objects.get_or_create(organization=org, name=n, defaults=dict(address=a, city=c, region=r))[0]
            for n, a, c, r in VENUES
        ]
        tz = timezone.get_current_timezone()
        for title, cat, vi, days, hour, length, summary, tickets in EVENTS:
            day = timezone.localdate() + timedelta(days=days)
            start = datetime.combine(day, time(hour), tzinfo=tz)
            ev = Event.objects.create(
                organization=org, title=title, summary=summary, description=summary,
                category=Category.objects.get(slug=cat), venue=venues[vi],
                start_at=start, end_at=start + timedelta(hours=length),
                status=EventStatus.PUBLISHED, published_at=timezone.now(), created_by=user,
                is_featured=days < 15,
            )
            for i, (name, price, qty) in enumerate(tickets):
                TicketType.objects.create(
                    event=ev, name=name, price=Decimal(price), quantity=qty, sort_order=i,
                    admits=int(name.split()[-1]) if name.split()[-1].isdigit() else 1,
                )
        afro = Event.objects.get(organization=org, title=EVENTS[0][0])
        PromoCode.objects.create(event=afro, code="AFRO20", discount_type="percent", amount=20, max_uses=100)
        self.stdout.write(self.style.SUCCESS(f"Created {len(EVENTS)} demo events for '{org.name}'."))
