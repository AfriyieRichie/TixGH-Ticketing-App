from django.core.management.base import BaseCommand

from apps.orders.services import expire_stale_orders


class Command(BaseCommand):
    help = "Mark unpaid orders whose ticket hold has lapsed as expired."

    def handle(self, *args, **opts):
        self.stdout.write(f"Expired {expire_stale_orders()} order(s).")
