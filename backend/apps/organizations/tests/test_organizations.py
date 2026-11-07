from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.organizations.models import Invitation, Membership, Organization, Role

User = get_user_model()
BASE = "/api/v1/organizations/"


class OrgTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", full_name="Owner")
        self.client.force_authenticate(self.owner)
        res = self.client.post(BASE, {"name": "Accra Live Events", "region": "greater_accra"})
        assert res.status_code == 201, res.data
        self.org = Organization.objects.get(slug=res.data["slug"])
        self.url = f"{BASE}{self.org.slug}/"

    def add_member(self, role, **user_kw):
        user = User.objects.create_user(**user_kw)
        m = Membership.objects.create(organization=self.org, user=user, role=role)
        return user, m

    def as_user(self, user):
        self.client.force_authenticate(user)


class OrganizationTests(OrgTestBase):
    def test_creator_becomes_owner(self):
        res = self.client.get(self.url)
        self.assertEqual(res.data["my_role"], "owner")
        self.assertIn("manage_payouts", res.data["my_permissions"])
        self.assertEqual(self.org.slug, "accra-live-events")

    def test_slugs_are_unique_and_avoid_reserved_words(self):
        res = self.client.post(BASE, {"name": "Accra Live Events"})
        self.assertEqual(res.data["slug"], "accra-live-events-2")
        res = self.client.post(BASE, {"name": "Public"})
        self.assertEqual(res.data["slug"], "public-2")

    def test_list_only_my_orgs(self):
        other = User.objects.create_user(email="other@example.com")
        Organization.objects.create(name="Not Mine", created_by=other)
        res = self.client.get(BASE)
        self.assertEqual([o["slug"] for o in res.data["results"]], ["accra-live-events"])

    def test_non_member_gets_404(self):
        self.as_user(User.objects.create_user(email="stranger@example.com"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url + "members/").status_code, 404)

    def test_scanner_cannot_edit_org(self):
        scanner, _ = self.add_member(Role.SCANNER, phone="0201111111")
        self.as_user(scanner)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.patch(self.url, {"name": "Hacked"}).status_code, 403)

    def test_organizer_cannot_change_own_fees_or_verification(self):
        self.client.patch(self.url, {"fee_percent_override": "0", "verification_status": "verified"})
        self.org.refresh_from_db()
        self.assertIsNone(self.org.fee_percent_override)
        self.assertEqual(self.org.verification_status, "unverified")

    def test_phone_is_normalized(self):
        res = self.client.patch(self.url, {"phone": "0241234567"})
        self.assertEqual(res.data["phone"], "+233241234567")

    def test_public_profile(self):
        self.client.force_authenticate(None)
        res = self.client.get(f"{BASE}public/{self.org.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("fee_percent_override", res.data)

    def test_submit_verification_requires_complete_profile(self):
        res = self.client.post(self.url + "submit-verification/")
        self.assertEqual(res.status_code, 400)
        self.client.patch(self.url, {"description": "Concerts", "phone": "0241234567"})
        self.client.post(
            self.url + "payout-accounts/",
            {"method": "mobile_money", "mobile_money_provider": "mtn",
             "account_number": "0241234567", "account_name": "Accra Live"},
        )
        res = self.client.post(self.url + "submit-verification/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["verification_status"], "pending")


class MemberTests(OrgTestBase):
    def test_admin_can_change_roles_but_not_owners(self):
        admin, _ = self.add_member(Role.ADMIN, email="admin@example.com")
        _, scanner_m = self.add_member(Role.SCANNER, email="scan@example.com")
        owner_m = Membership.objects.get(user=self.owner)
        self.as_user(admin)
        res = self.client.patch(f"{self.url}members/{scanner_m.pk}/", {"role": "marketing"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.patch(f"{self.url}members/{scanner_m.pk}/", {"role": "owner"}).status_code, 403)
        self.assertEqual(self.client.delete(f"{self.url}members/{owner_m.pk}/").status_code, 403)

    def test_last_owner_cannot_leave_or_be_demoted(self):
        owner_m = Membership.objects.get(user=self.owner)
        self.assertEqual(self.client.patch(f"{self.url}members/{owner_m.pk}/", {"role": "admin"}).status_code, 400)
        self.assertEqual(self.client.delete(f"{self.url}members/{owner_m.pk}/").status_code, 400)

    def test_member_can_leave(self):
        scanner, m = self.add_member(Role.SCANNER, email="scan@example.com")
        self.as_user(scanner)
        self.assertEqual(self.client.delete(f"{self.url}members/{m.pk}/").status_code, 204)

    def test_scanner_cannot_remove_others(self):
        scanner, _ = self.add_member(Role.SCANNER, email="scan@example.com")
        _, other = self.add_member(Role.MARKETING, email="mk@example.com")
        self.as_user(scanner)
        self.assertEqual(self.client.delete(f"{self.url}members/{other.pk}/").status_code, 403)


@patch("apps.organizations.views.send_sms")
@patch("apps.organizations.views.send_email")
class InvitationTests(OrgTestBase):
    def test_invite_and_accept_by_phone(self, send_email, send_sms):
        res = self.client.post(self.url + "invitations/", {"contact": "0551234567", "role": "scanner"})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["contact"], "+233551234567")
        self.assertFalse(res.data["delivery_failed"])
        send_sms.assert_called_once()
        token = Invitation.objects.get().token

        invitee = User.objects.create_user(phone="0551234567")
        self.client.force_authenticate(None)
        preview = self.client.get(f"{BASE}invitations/{token}/")
        self.assertEqual(preview.data["organization"]["name"], "Accra Live Events")

        self.as_user(invitee)
        res = self.client.post(f"{BASE}invitations/{token}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["my_role"], "scanner")
        # Cannot be reused.
        self.assertEqual(self.client.post(f"{BASE}invitations/{token}/").status_code, 400)

    def test_wrong_account_cannot_accept(self, send_email, send_sms):
        self.client.post(self.url + "invitations/", {"contact": "x@example.com", "role": "admin"})
        token = Invitation.objects.get().token
        self.as_user(User.objects.create_user(email="y@example.com"))
        self.assertEqual(self.client.post(f"{BASE}invitations/{token}/").status_code, 403)

    def test_only_owner_can_invite_owner(self, send_email, send_sms):
        admin, _ = self.add_member(Role.ADMIN, email="admin@example.com")
        self.as_user(admin)
        res = self.client.post(self.url + "invitations/", {"contact": "z@example.com", "role": "owner"})
        self.assertEqual(res.status_code, 403)

    def test_cannot_invite_existing_member(self, send_email, send_sms):
        res = self.client.post(self.url + "invitations/", {"contact": "owner@example.com", "role": "admin"})
        self.assertEqual(res.status_code, 400)

    def test_revoked_invite_cannot_be_accepted(self, send_email, send_sms):
        res = self.client.post(self.url + "invitations/", {"contact": "x@example.com", "role": "admin"})
        self.client.delete(f"{self.url}invitations/{res.data['id']}/")
        token = Invitation.objects.get().token
        self.as_user(User.objects.create_user(email="x@example.com"))
        self.assertEqual(self.client.post(f"{BASE}invitations/{token}/").status_code, 400)


class PayoutAccountTests(OrgTestBase):
    momo = {
        "method": "mobile_money", "mobile_money_provider": "mtn",
        "account_number": "+233241234567", "account_name": "Accra Live",
    }
    bank = {
        "method": "bank", "bank_name": "GCB Bank", "bank_code": "040100",
        "account_number": "1234567890123", "account_name": "Accra Live Ltd",
    }

    def test_first_account_is_default_and_number_is_local(self):
        res = self.client.post(self.url + "payout-accounts/", self.momo)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["is_default"])
        self.assertEqual(res.data["account_number"], "0241234567")

    def test_only_one_default(self):
        first = self.client.post(self.url + "payout-accounts/", self.momo).data
        second = self.client.post(self.url + "payout-accounts/", {**self.bank, "is_default": True}).data
        self.assertTrue(second["is_default"])
        accounts = {a["id"]: a for a in self.client.get(self.url + "payout-accounts/").data}
        self.assertFalse(accounts[first["id"]]["is_default"])

    def test_validation(self):
        res = self.client.post(self.url + "payout-accounts/", {**self.momo, "mobile_money_provider": ""})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(self.url + "payout-accounts/", {**self.bank, "bank_code": ""})
        self.assertEqual(res.status_code, 400)

    def test_role_access(self):
        self.client.post(self.url + "payout-accounts/", self.momo)
        finance, _ = self.add_member(Role.FINANCE, email="fin@example.com")
        admin, _ = self.add_member(Role.ADMIN, email="admin@example.com")
        marketing, _ = self.add_member(Role.MARKETING, email="mk@example.com")
        self.as_user(finance)
        self.assertEqual(self.client.post(self.url + "payout-accounts/", self.bank).status_code, 201)
        self.as_user(admin)  # can view, cannot change
        self.assertEqual(self.client.get(self.url + "payout-accounts/").status_code, 200)
        self.assertEqual(self.client.post(self.url + "payout-accounts/", self.bank).status_code, 403)
        self.as_user(marketing)
        self.assertEqual(self.client.get(self.url + "payout-accounts/").status_code, 403)

    def test_changing_number_resets_verification(self):
        acc = self.client.post(self.url + "payout-accounts/", self.momo).data
        self.org.payout_accounts.update(is_verified=True, gateway_subaccount_code="ACCT_x")
        self.client.patch(f"{self.url}payout-accounts/{acc['id']}/", {"account_number": "0201234567"})
        a = self.org.payout_accounts.get()
        self.assertFalse(a.is_verified)
        self.assertEqual(a.gateway_subaccount_code, "")

    def test_cannot_delete_default_when_others_exist(self):
        acc = self.client.post(self.url + "payout-accounts/", self.momo).data
        self.client.post(self.url + "payout-accounts/", self.bank)
        self.assertEqual(self.client.delete(f"{self.url}payout-accounts/{acc['id']}/").status_code, 400)
