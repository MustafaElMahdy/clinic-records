import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Clinic(models.Model):
    class SubscriptionStatus(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)

    trial_ends_at = models.DateField(null=True, blank=True)
    paid_until = models.DateField(
        null=True, blank=True,
        help_text="Active subscriptions are allowed access through this date.",
    )
    subscription_status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def is_access_allowed(self):
        today = timezone.now().date()
        if self.subscription_status == self.SubscriptionStatus.ACTIVE:
            # "active" means paid through paid_until, not active forever
            return self.paid_until is not None and self.paid_until >= today
        if self.subscription_status == self.SubscriptionStatus.TRIALING:
            return self.trial_ends_at is not None and self.trial_ends_at >= today
        return False

    @property
    def trial_days_remaining(self):
        if self.subscription_status != self.SubscriptionStatus.TRIALING or not self.trial_ends_at:
            return 0
        delta = self.trial_ends_at - timezone.now().date()
        return max(delta.days, 0)

    @property
    def paid_days_remaining(self):
        if self.subscription_status != self.SubscriptionStatus.ACTIVE or not self.paid_until:
            return 0
        delta = self.paid_until - timezone.now().date()
        return max(delta.days, 0)

    def activate_for_days(self, days=30):
        """Extend access by `days`. Stacks onto remaining time on early renewal."""
        today = timezone.now().date()
        base = self.paid_until if (self.paid_until and self.paid_until >= today) else today
        self.paid_until = base + timedelta(days=days)
        self.subscription_status = self.SubscriptionStatus.ACTIVE
        self.save(update_fields=["paid_until", "subscription_status"])


def payment_proof_upload_path(instance, filename):
    """media path: payment_proofs/clinic_{id}/{timestamp}{ext}"""
    _, ext = os.path.splitext(filename)
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"payment_proofs/clinic_{instance.clinic_id}/{stamp}{ext}"


class PaymentSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="payment_submissions"
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=1500)
    reference = models.CharField(
        max_length=100,
        help_text="InstaPay transaction reference provided by the clinic",
    )
    screenshot = models.FileField(
        upload_to=payment_proof_upload_path, null=True, blank=True,
        help_text="Optional screenshot of the InstaPay transfer",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    note = models.TextField(blank=True, help_text="Internal note / rejection reason")

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payment_submissions",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_payments",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.clinic.name} — {self.amount} EGP — {self.get_status_display()}"

    def approve(self, reviewed_by=None, days=30):
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self.clinic.activate_for_days(days)

    def reject(self, reviewed_by=None, note=""):
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        if note:
            self.note = note
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "note"])


class RenewalReminder(models.Model):
    """
    One row per reminder actually sent. Used to make the daily reminder command
    idempotent: a given (clinic, kind, period_end, days_before) is emailed once.
    Because period_end is the trial_ends_at / paid_until value, the dedup resets
    naturally each cycle when the clinic renews and that date changes.
    """
    class Kind(models.TextChoices):
        TRIAL = "trial", "Trial ending"
        PAID = "paid", "Paid subscription ending"

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="renewal_reminders"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    period_end = models.DateField(help_text="The trial_ends_at / paid_until this reminder was for")
    days_before = models.PositiveSmallIntegerField(help_text="Days before period_end (0 = on the day)")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clinic", "kind", "period_end", "days_before"],
                name="unique_reminder_per_period_offset",
            )
        ]

    def __str__(self):
        return f"{self.clinic.name} — {self.kind} — {self.days_before}d before {self.period_end}"


class ClickEvent(models.Model):
    """
    First-party, anonymous click tracking for marketing-page CTAs. Records only
    an allowlisted event name + the page path + timestamp. No cookies, no PII,
    no per-user profiling — consistent with the Privacy Policy.
    """
    name = models.CharField(max_length=50, db_index=True)
    page = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} @ {self.created_at:%Y-%m-%d %H:%M}"