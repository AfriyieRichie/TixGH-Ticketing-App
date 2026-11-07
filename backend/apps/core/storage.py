"""
Store uploaded images (event covers, organizer logos) on Cloudinary.

Free hosts such as Render wipe their local disk on every restart, so uploads
must live elsewhere. The cloudinary SDK reads CLOUDINARY_URL from the
environment. Images are served through Cloudinary's CDN with automatic
format/quality, which keeps them small on slow mobile networks.
"""

import os
import secrets

import cloudinary.uploader
import cloudinary.utils
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    def _split(self, name: str) -> tuple[str, str]:
        public_id, ext = os.path.splitext(name)
        return public_id, ext.lstrip(".")

    def _save(self, name, content):
        base, _ = self._split(name)
        public_id = f"{settings.CLOUDINARY_FOLDER}/{base}_{secrets.token_hex(4)}"
        content.seek(0)
        result = cloudinary.uploader.upload(
            content, public_id=public_id, resource_type="image", overwrite=False, unique_filename=False
        )
        return f"{result['public_id']}.{result['format']}"

    def url(self, name):
        public_id, ext = self._split(name)
        url, _ = cloudinary.utils.cloudinary_url(
            public_id, format=ext or None, secure=True, quality="auto", fetch_format="auto"
        )
        return url

    def exists(self, name):
        return False  # _save always makes the name unique

    def delete(self, name):
        public_id, _ = self._split(name)
        cloudinary.uploader.destroy(public_id, resource_type="image")

    def size(self, name):
        return 0

    def get_available_name(self, name, max_length=None):
        return name

