import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import OTPCode
from apps.core.phone import InvalidPhoneNumber, normalize_phone

User = get_user_model()


class PhoneNormalizationTests(APITestCase):
    def test_local_and_international_formats(self):
        for raw in ("0241234567", "024 123 4567", "+233241234567", "233241234567"):
            self.assertEqual(normalize_phone(raw), "+233241234567", raw)

    def test_invalid(self):
        for raw in ("", "12345", "abc"):
            with self.assertRaises(InvalidPhoneNumber):
                normalize_phone(raw)


class OTPMixin:
    def setUp(self):
        cache.clear()
        self.sent = []
        sms = patch("apps.accounts.otp.send_sms", side_effect=lambda to, msg: self.sent.append((to, msg)))
        mail = patch(
            "apps.accounts.otp.send_email",
            side_effect=lambda to, subj, body: self.sent.append((to, body)),
        )
        sms.start(), mail.start()
        self.addCleanup(sms.stop), self.addCleanup(mail.stop)

    def request_code(self, identifier, purpose="login", **kw):
        return self.client.post(
            "/api/v1/auth/otp/request/", {"identifier": identifier, "purpose": purpose}, **kw
        )

    def last_code(self):
        return re.search(r"\b(\d{6})\b", self.sent[-1][1]).group(1)


class OTPLoginTests(OTPMixin, APITestCase):
    def test_phone_signup_then_login(self):
        res = self.request_code("0241234567")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["channel"], "sms")
        self.assertEqual(self.sent[-1][0], "+233241234567")

        res = self.client.post(
            "/api/v1/auth/otp/verify/",
            {"identifier": "024 123 4567", "code": self.last_code(), "full_name": "Ama Mensah"},
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["is_new_user"])
        self.assertEqual(res.data["user"]["phone"], "+233241234567")
        self.assertTrue(res.data["user"]["phone_verified"])
        self.assertFalse(res.data["user"]["has_password"])

        # Second login: same account, not new.
        self.request_code("+233241234567")
        res = self.client.post(
            "/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": self.last_code()}
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["is_new_user"])
        self.assertEqual(User.objects.count(), 1)

    def test_email_login_is_case_insensitive(self):
        User.objects.create_user(email="kofi@example.com")
        self.request_code("Kofi@Example.com")
        res = self.client.post(
            "/api/v1/auth/otp/verify/", {"identifier": "KOFI@example.com", "code": self.last_code()}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_code_is_single_use(self):
        self.request_code("0241234567")
        code = self.last_code()
        payload = {"identifier": "0241234567", "code": code}
        self.assertEqual(self.client.post("/api/v1/auth/otp/verify/", payload).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/otp/verify/", payload).status_code, 400)

    def test_wrong_attempts_are_counted_and_lock_the_code(self):
        self.request_code("0241234567")
        good = self.last_code()
        bad = "000000" if good != "000000" else "111111"
        for _ in range(5):
            res = self.client.post("/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": bad})
            self.assertEqual(res.status_code, 400)
        self.assertEqual(OTPCode.objects.get().attempts, 5)
        res = self.client.post("/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": good})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Too many", str(res.data))

    def test_expired_code_rejected(self):
        self.request_code("0241234567")
        OTPCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        res = self.client.post(
            "/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": self.last_code()}
        )
        self.assertEqual(res.status_code, 400)

    def test_new_code_voids_old_code(self):
        self.request_code("0241234567")
        old = self.last_code()
        self.request_code("0241234567")
        new = self.last_code()
        if old != new:
            res = self.client.post("/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": old})
            self.assertEqual(res.status_code, 400)

    def test_hourly_limit(self):
        with self.settings(OTP_MAX_PER_HOUR=2):
            self.assertEqual(self.request_code("0241234567").status_code, 200)
            cache.clear()
            self.assertEqual(self.request_code("0241234567").status_code, 200)
            cache.clear()
            self.assertEqual(self.request_code("0241234567").status_code, 429)

    def test_invalid_phone(self):
        res = self.request_code("12345")
        self.assertEqual(res.status_code, 400)

    def test_codes_are_not_stored_in_plain_text(self):
        self.request_code("0241234567")
        self.assertNotEqual(OTPCode.objects.get().code_hash, self.last_code())

    def test_disabled_user_cannot_log_in(self):
        User.objects.create_user(phone="0241234567", is_active=False)
        self.request_code("0241234567")
        res = self.client.post(
            "/api/v1/auth/otp/verify/", {"identifier": "0241234567", "code": self.last_code()}
        )
        self.assertEqual(res.status_code, 403)


class PasswordTests(OTPMixin, APITestCase):
    def test_password_login_with_email_or_phone(self):
        User.objects.create_user(email="ama@example.com", phone="0241234567", password="S3cure-pass!")
        for ident in ("ama@example.com", "0241234567", "+233241234567"):
            res = self.client.post("/api/v1/auth/login/", {"identifier": ident, "password": "S3cure-pass!"})
            self.assertEqual(res.status_code, 200, ident)
            self.assertIn("access", res.data)
        res = self.client.post("/api/v1/auth/login/", {"identifier": "ama@example.com", "password": "wrong"})
        self.assertEqual(res.status_code, 401)

    def test_otp_user_can_set_password_without_current(self):
        user = User.objects.create_user(phone="0241234567")
        self.client.force_authenticate(user)
        res = self.client.post("/api/v1/auth/password/change/", {"new_password": "Brand-new-pass9"})
        self.assertEqual(res.status_code, 204)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Brand-new-pass9"))

    def test_change_requires_current_password(self):
        user = User.objects.create_user(email="a@example.com", password="Old-pass-123")
        self.client.force_authenticate(user)
        res = self.client.post(
            "/api/v1/auth/password/change/", {"current_password": "nope", "new_password": "New-pass-456"}
        )
        self.assertEqual(res.status_code, 400)

    def test_reset_flow(self):
        user = User.objects.create_user(email="a@example.com", password="Old-pass-123")
        self.request_code("a@example.com", purpose="password_reset")
        code = self.last_code()
        # Weak password is rejected without burning the code.
        res = self.client.post(
            "/api/v1/auth/password/reset/",
            {"identifier": "a@example.com", "code": code, "new_password": "123"},
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/v1/auth/password/reset/",
            {"identifier": "a@example.com", "code": code, "new_password": "Fresh-pass-789"},
        )
        self.assertEqual(res.status_code, 204)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Fresh-pass-789"))

    def test_reset_does_not_reveal_unknown_accounts(self):
        res = self.request_code("ghost@example.com", purpose="password_reset")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.sent, [])


class ProfileAndContactTests(OTPMixin, APITestCase):
    def test_me_and_update(self):
        user = User.objects.create_user(phone="0241234567")
        self.client.force_authenticate(user)
        res = self.client.patch("/api/v1/auth/me/", {"full_name": "Yaw Boateng", "phone": "+233200000000"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["full_name"], "Yaw Boateng")
        self.assertEqual(res.data["phone"], "+233241234567")  # read-only

    def test_attach_email_with_otp(self):
        user = User.objects.create_user(phone="0241234567")
        self.client.force_authenticate(user)
        self.request_code("yaw@example.com", purpose="verify_contact")
        res = self.client.post(
            "/api/v1/auth/me/contact/", {"identifier": "yaw@example.com", "code": self.last_code()}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["email"], "yaw@example.com")
        self.assertTrue(res.data["email_verified"])

    def test_cannot_attach_contact_owned_by_someone_else(self):
        User.objects.create_user(email="taken@example.com")
        user = User.objects.create_user(phone="0241234567")
        self.client.force_authenticate(user)
        res = self.request_code("taken@example.com", purpose="verify_contact")
        self.assertEqual(res.status_code, 400)

    def test_verify_contact_requires_login(self):
        res = self.request_code("x@example.com", purpose="verify_contact")
        self.assertEqual(res.status_code, 401)

    def test_logout_blacklists_refresh(self):
        User.objects.create_user(email="a@example.com", password="Old-pass-123")
        tokens = self.client.post(
            "/api/v1/auth/login/", {"identifier": "a@example.com", "password": "Old-pass-123"}
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code, 205)
        res = self.client.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(res.status_code, 401)
