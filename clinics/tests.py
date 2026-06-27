from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from clinics.admin import PaymentSubmissionAdmin
from clinics.models import Clinic, PaymentSubmission


def make_clinic(**kwargs):
    defaults = dict(
        name="Test Clinic",
        subscription_status=Clinic.SubscriptionStatus.TRIALING,
    )
    defaults.update(kwargs)
    return Clinic.objects.create(**defaults)


class ClinicAccessModelTests(TestCase):
    """is_access_allowed gating + activate_for_days date math."""

    def setUp(self):
        self.today = timezone.now().date()

    def test_expired_clinic_blocked(self):
        c = make_clinic(subscription_status="expired")
        self.assertFalse(c.is_access_allowed)

    def test_trialing_within_trial_allowed(self):
        c = make_clinic(trial_ends_at=self.today + timedelta(days=5))
        self.assertTrue(c.is_access_allowed)

    def test_trialing_past_trial_blocked(self):
        c = make_clinic(trial_ends_at=self.today - timedelta(days=1))
        self.assertFalse(c.is_access_allowed)

    def test_active_with_future_paid_until_allowed(self):
        c = make_clinic(subscription_status="active", paid_until=self.today + timedelta(days=10))
        self.assertTrue(c.is_access_allowed)

    def test_active_with_past_paid_until_blocked(self):
        c = make_clinic(subscription_status="active", paid_until=self.today - timedelta(days=1))
        self.assertFalse(c.is_access_allowed)

    def test_active_without_paid_until_blocked(self):
        # The bug the backfill migration guards against: active but no date = no access.
        c = make_clinic(subscription_status="active", paid_until=None)
        self.assertFalse(c.is_access_allowed)

    def test_activate_for_days_from_scratch(self):
        c = make_clinic(subscription_status="expired")
        c.activate_for_days(30)
        self.assertEqual(c.subscription_status, "active")
        self.assertEqual(c.paid_until, self.today + timedelta(days=30))

    def test_activate_for_days_stacks_on_early_renewal(self):
        c = make_clinic(subscription_status="active", paid_until=self.today + timedelta(days=30))
        c.activate_for_days(30)
        self.assertEqual(c.paid_until, self.today + timedelta(days=60))

    def test_activate_for_days_from_lapsed_starts_today(self):
        c = make_clinic(subscription_status="active", paid_until=self.today - timedelta(days=10))
        c.activate_for_days(30)
        self.assertEqual(c.paid_until, self.today + timedelta(days=30))

    def test_paid_days_remaining(self):
        c = make_clinic(subscription_status="active", paid_until=self.today + timedelta(days=15))
        self.assertEqual(c.paid_days_remaining, 15)

    def test_paid_days_remaining_zero_when_trialing(self):
        c = make_clinic(trial_ends_at=self.today + timedelta(days=5))
        self.assertEqual(c.paid_days_remaining, 0)


class PaymentSubmissionModelTests(TestCase):
    def setUp(self):
        self.clinic = make_clinic(subscription_status="expired")
        self.user = User.objects.create_user(
            username="admin@x.com", password="pw", role="admin", clinic=self.clinic
        )

    def test_approve_activates_clinic(self):
        sub = PaymentSubmission.objects.create(clinic=self.clinic, reference="REF1")
        sub.approve(reviewed_by=self.user, days=30)
        sub.refresh_from_db()
        self.clinic.refresh_from_db()
        self.assertEqual(sub.status, PaymentSubmission.Status.APPROVED)
        self.assertEqual(sub.reviewed_by, self.user)
        self.assertIsNotNone(sub.reviewed_at)
        self.assertEqual(self.clinic.subscription_status, "active")
        self.assertTrue(self.clinic.is_access_allowed)

    def test_reject_keeps_clinic_blocked(self):
        sub = PaymentSubmission.objects.create(clinic=self.clinic, reference="REF2")
        sub.reject(reviewed_by=self.user, note="reference not found")
        sub.refresh_from_db()
        self.clinic.refresh_from_db()
        self.assertEqual(sub.status, PaymentSubmission.Status.REJECTED)
        self.assertEqual(sub.note, "reference not found")
        self.assertFalse(self.clinic.is_access_allowed)


@override_settings(
    INSTAPAY_ADDRESS="test@instapay",
    MONTHLY_PRICE_EGP=1500,
    PAYMENT_NOTIFICATION_EMAIL="owner@documed.health",
)
class SubscriptionFlowTests(TestCase):
    """End-to-end: blocked clinic -> pay -> approve -> access restored."""

    def setUp(self):
        self.clinic = make_clinic(subscription_status="expired")
        self.user = User.objects.create_user(
            username="admin@x.com", password="pw", role="admin",
            clinic=self.clinic, email="doc@clinic.com",
        )
        self.client.force_login(self.user)

    def test_blocked_clinic_redirected_to_subscription(self):
        resp = self.client.get(reverse("patients:list"))
        self.assertRedirects(resp, reverse("clinics:subscription"))

    def test_subscription_page_shows_instapay_address(self):
        resp = self.client.get(reverse("clinics:subscription"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "test@instapay")

    def test_submitting_payment_creates_pending_and_emails_owner(self):
        resp = self.client.post(reverse("clinics:subscription"), {"reference": "TXN-123"})
        self.assertRedirects(resp, reverse("clinics:subscription"))

        sub = PaymentSubmission.objects.get(clinic=self.clinic)
        self.assertEqual(sub.reference, "TXN-123")
        self.assertEqual(sub.status, PaymentSubmission.Status.PENDING)
        self.assertEqual(sub.submitted_by, self.user)
        self.assertEqual(sub.amount, 1500)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("owner@documed.health", mail.outbox[0].to)
        self.assertIn("TXN-123", mail.outbox[0].body)

    def test_pending_submission_hides_form(self):
        PaymentSubmission.objects.create(
            clinic=self.clinic, reference="X", submitted_by=self.user
        )
        resp = self.client.get(reverse("clinics:subscription"))
        self.assertNotContains(resp, 'name="reference"')

    def test_approved_payment_restores_access(self):
        sub = PaymentSubmission.objects.create(clinic=self.clinic, reference="X")
        sub.approve(reviewed_by=self.user)
        resp = self.client.get(reverse("patients:list"))
        self.assertEqual(resp.status_code, 200)


class AdminApproveActionTests(TestCase):
    def setUp(self):
        self.clinic = make_clinic(subscription_status="expired")
        self.clinic_admin = User.objects.create_user(
            username="owner", password="pw", role="admin",
            clinic=self.clinic, email="clinic@x.com",
        )
        self.superuser = User.objects.create_superuser(
            username="root", password="pw", email="root@x.com"
        )
        self.factory = RequestFactory()

    def _admin_request(self):
        req = self.factory.post("/admin/")
        req.user = self.superuser
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def test_approve_action_activates_clinic_and_emails_it(self):
        sub = PaymentSubmission.objects.create(clinic=self.clinic, reference="R")
        admin = PaymentSubmissionAdmin(PaymentSubmission, AdminSite())
        admin.approve_payments(self._admin_request(), PaymentSubmission.objects.filter(pk=sub.pk))

        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.subscription_status, "active")
        self.assertTrue(self.clinic.is_access_allowed)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("clinic@x.com", mail.outbox[0].to)

    def test_reject_action_leaves_clinic_blocked(self):
        sub = PaymentSubmission.objects.create(clinic=self.clinic, reference="R")
        admin = PaymentSubmissionAdmin(PaymentSubmission, AdminSite())
        admin.reject_payments(self._admin_request(), PaymentSubmission.objects.filter(pk=sub.pk))

        sub.refresh_from_db()
        self.clinic.refresh_from_db()
        self.assertEqual(sub.status, PaymentSubmission.Status.REJECTED)
        self.assertFalse(self.clinic.is_access_allowed)
