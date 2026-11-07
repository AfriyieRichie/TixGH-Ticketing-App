from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.core.models import PlatformSettings


class FeeTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_default_fee(self):
        ps = PlatformSettings.load()
        self.assertEqual(ps.ticket_fee(Decimal("100")), Decimal("6.00"))  # 5% + GHS 1
        self.assertEqual(ps.ticket_fee(Decimal("0")), Decimal("0.00"))  # free tickets
        self.assertEqual(ps.ticket_fee(Decimal("33.33")), Decimal("2.67"))

    def test_fee_cap(self):
        ps = PlatformSettings.load()
        ps.fee_cap = Decimal("50")
        ps.save()
        self.assertEqual(PlatformSettings.load().ticket_fee(Decimal("5000")), Decimal("50.00"))

    def test_singleton(self):
        PlatformSettings.load()
        PlatformSettings(fee_percent=Decimal("4")).save()
        self.assertEqual(PlatformSettings.objects.count(), 1)
        self.assertEqual(PlatformSettings.load().fee_percent, Decimal("4"))


class PublicEndpointTests(APITestCase):
    def test_health_and_config(self):
        self.assertEqual(self.client.get("/api/v1/health/").data, {"status": "ok"})
        res = self.client.get("/api/v1/config/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["currency"], "GHS")
        self.assertEqual(len(res.data["regions"]), 16)
