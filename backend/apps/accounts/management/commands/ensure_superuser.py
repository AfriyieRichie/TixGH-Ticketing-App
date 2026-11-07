"""
Create the platform admin from environment variables if it doesn't exist.
Runs on every deploy (hosts like Render's free plan have no shell access).

    DJANGO_SUPERUSER_EMAIL=you@example.com DJANGO_SUPERUSER_PASSWORD=... python manage.py ensure_superuser
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the admin account from DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD (idempotent)."

    def handle(self, *args, **opts):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not email or not password:
            self.stdout.write("DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipping.")
            return
        User = get_user_model()
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"Admin {email} already exists.")
            return
        User.objects.create_superuser(email=email, password=password, full_name="Platform Admin")
        self.stdout.write(self.style.SUCCESS(f"Created admin {email}."))
