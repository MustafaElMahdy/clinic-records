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
        if self.subscription_status == self.SubscriptionStatus.ACTIVE:
            return True
        if self.subscription_status == self.SubscriptionStatus.TRIALING:
            return self.trial_ends_at is not None and self.trial_ends_at >= timezone.now().date()
        return False

    @property
    def trial_days_remaining(self):
        if self.subscription_status != self.SubscriptionStatus.TRIALING or not self.trial_ends_at:
            return 0
        delta = self.trial_ends_at - timezone.now().date()
        return max(delta.days, 0)