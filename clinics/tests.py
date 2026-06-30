from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from clinics.admin import PaymentSubmissionAdmin
from clinics.models import Clinic, PaymentSubmission, RenewalReminder


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


@override_settings(
    INSTAPAY_ADDRESS="test@instapay",
    MONTHLY_PRICE_EGP=1500,
    SITE_URL="https://documed.health",
)
class RenewalReminderCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

    def _clinic_with_admin(self, **kwargs):
        clinic = make_clinic(**kwargs)
        User.objects.create_user(
            username=f"admin{clinic.pk}@x.com", password="pw", role="admin",
            clinic=clinic, email=f"admin{clinic.pk}@x.com",
        )
        return clinic

    def test_paid_reminder_3_days_before(self):
        c = self._clinic_with_admin(
            subscription_status="active", paid_until=self.today + timedelta(days=3)
        )
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(c.renewal_reminders.count(), 1)
        r = c.renewal_reminders.get()
        self.assertEqual(r.kind, RenewalReminder.Kind.PAID)
        self.assertEqual(r.days_before, 3)

    def test_paid_reminder_day_of(self):
        c = self._clinic_with_admin(
            subscription_status="active", paid_until=self.today
        )
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(c.renewal_reminders.get().days_before, 0)

    def test_trial_reminder(self):
        c = self._clinic_with_admin(trial_ends_at=self.today + timedelta(days=3))
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(c.renewal_reminders.get().kind, RenewalReminder.Kind.TRIAL)

    def test_no_reminder_outside_window(self):
        self._clinic_with_admin(
            subscription_status="active", paid_until=self.today + timedelta(days=5)
        )
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 0)

    def test_idempotent_no_duplicate_on_second_run(self):
        c = self._clinic_with_admin(
            subscription_status="active", paid_until=self.today + timedelta(days=3)
        )
        call_command("send_renewal_reminders")
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(c.renewal_reminders.count(), 1)

    def test_pending_payment_suppresses_reminder(self):
        c = self._clinic_with_admin(
            subscription_status="active", paid_until=self.today + timedelta(days=3)
        )
        PaymentSubmission.objects.create(clinic=c, reference="ALREADY-PAID")
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(c.renewal_reminders.count(), 0)

    def test_no_email_recipient_skips_without_recording(self):
        # Clinic whose only user has no email -> can't notify, don't record so it retries.
        c = make_clinic(subscription_status="active", paid_until=self.today + timedelta(days=3))
        User.objects.create_user(username="noemail", password="pw", role="admin", clinic=c)
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(c.renewal_reminders.count(), 0)

    def test_dry_run_sends_nothing_and_records_nothing(self):
        c = self._clinic_with_admin(
            subscription_status="active", paid_until=self.today + timedelta(days=3)
        )
        call_command("send_renewal_reminders", "--dry-run")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(c.renewal_reminders.count(), 0)

    def test_expired_clinic_gets_no_reminder(self):
        # Already locked out -> this is win-back, not a reminder; out of scope.
        self._clinic_with_admin(
            subscription_status="expired", paid_until=self.today - timedelta(days=1)
        )
        call_command("send_renewal_reminders")
        self.assertEqual(len(mail.outbox), 0)


class PurgeCancelledClinicsTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

    def _populate(self, clinic):
        """Give a clinic a user, patient, visit, and audit event."""
        user = User.objects.create_user(
            username=f"u{clinic.pk}", password="pw", role="admin", clinic=clinic
        )
        from patients.models import Patient
        from visits.models import Visit
        p = Patient.objects.create(clinic=clinic, full_name="Test P", normalized_name="test p")
        Visit.objects.create(clinic=clinic, patient=p, clinical_notes="x")
        return user, p

    def test_clinic_past_window_is_purged_with_commit(self):
        from patients.models import Patient
        c = make_clinic(subscription_status="expired",
                        paid_until=self.today - timedelta(days=100))
        self._populate(c)
        cid = c.pk
        call_command("purge_cancelled_clinics", "--commit")
        self.assertFalse(Clinic.objects.filter(pk=cid).exists())
        self.assertFalse(Patient.objects.filter(clinic_id=cid).exists())
        self.assertFalse(User.objects.filter(clinic_id=cid).exists())

    def test_dry_run_deletes_nothing(self):
        c = make_clinic(subscription_status="expired",
                        paid_until=self.today - timedelta(days=100))
        self._populate(c)
        cid = c.pk
        call_command("purge_cancelled_clinics")  # no --commit
        self.assertTrue(Clinic.objects.filter(pk=cid).exists())

    def test_recently_cancelled_clinic_is_kept(self):
        c = make_clinic(subscription_status="expired",
                        paid_until=self.today - timedelta(days=30))
        cid = c.pk
        call_command("purge_cancelled_clinics", "--commit")
        self.assertTrue(Clinic.objects.filter(pk=cid).exists())

    def test_active_clinic_is_never_purged(self):
        c = make_clinic(subscription_status="active",
                        paid_until=self.today + timedelta(days=10))
        cid = c.pk
        call_command("purge_cancelled_clinics", "--commit")
        self.assertTrue(Clinic.objects.filter(pk=cid).exists())

    def test_clinic_without_end_dates_is_skipped(self):
        # Safety guard: no paid_until/trial_ends_at -> never auto-deleted.
        c = make_clinic(subscription_status="expired", paid_until=None, trial_ends_at=None)
        cid = c.pk
        call_command("purge_cancelled_clinics", "--commit")
        self.assertTrue(Clinic.objects.filter(pk=cid).exists())

    def test_trial_ended_long_ago_is_purged(self):
        c = make_clinic(subscription_status="trialing",
                        trial_ends_at=self.today - timedelta(days=120))
        cid = c.pk
        call_command("purge_cancelled_clinics", "--commit")
        self.assertFalse(Clinic.objects.filter(pk=cid).exists())


class OwnerDashboardTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.clinic = make_clinic(subscription_status="active",
                                  paid_until=self.today + timedelta(days=10))
        self.superuser = User.objects.create_superuser("root", "root@x.com", "pw")
        self.normal = User.objects.create_user(
            "doc", password="pw", role="admin", clinic=self.clinic
        )

    def test_superuser_can_view(self):
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Paying customers")

    def test_non_superuser_cannot_view(self):
        self.client.force_login(self.normal)
        r = self.client.get(reverse("owner_dashboard"))
        self.assertNotEqual(r.status_code, 200)

    def test_anonymous_cannot_view(self):
        r = self.client.get(reverse("owner_dashboard"))
        self.assertNotEqual(r.status_code, 200)

    def test_metric_counts(self):
        make_clinic(subscription_status="trialing",
                    trial_ends_at=self.today + timedelta(days=5))
        make_clinic(subscription_status="trialing",
                    trial_ends_at=self.today - timedelta(days=1))  # lapsed trial
        self.client.force_login(self.superuser)
        r = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(r.context["paying"], 1)
        self.assertEqual(r.context["active_trials"], 1)
        self.assertEqual(r.context["lapsed_trials"], 1)
        self.assertEqual(r.context["mrr"], 1 * 1500)


class ClickTrackingTests(TestCase):
    def test_allowlisted_event_is_recorded(self):
        from clinics.models import ClickEvent
        r = self.client.post(reverse("track_event"),
                             {"name": "trial_hero", "page": "/"})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(ClickEvent.objects.filter(name="trial_hero").count(), 1)

    def test_unknown_event_is_ignored(self):
        from clinics.models import ClickEvent
        r = self.client.post(reverse("track_event"),
                             {"name": "evil_payload", "page": "/"})
        self.assertEqual(r.status_code, 204)  # still 204, but nothing stored
        self.assertEqual(ClickEvent.objects.count(), 0)

    def test_get_not_allowed(self):
        r = self.client.get(reverse("track_event"))
        self.assertEqual(r.status_code, 405)

    def test_clicks_show_on_dashboard(self):
        from clinics.models import ClickEvent
        ClickEvent.objects.create(name="trial_hero", page="/")
        ClickEvent.objects.create(name="trial_hero", page="/")
        ClickEvent.objects.create(name="nav_pricing", page="/")
        su = User.objects.create_superuser("root2", "root2@x.com", "pw")
        self.client.force_login(su)
        r = self.client.get(reverse("owner_dashboard"))
        rows = {row["label"]: row["total"] for row in r.context["click_rows"]}
        self.assertEqual(rows["Start trial · hero"], 2)
        self.assertEqual(rows["Nav: Pricing"], 1)
