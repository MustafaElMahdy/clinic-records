from django.conf import settings
from django.contrib import admin
from django.core.mail import send_mail

from .models import Clinic, PaymentSubmission, RenewalReminder


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "subscription_status", "trial_ends_at",
        "paid_until", "days_remaining", "phone", "created_at",
    )
    list_filter = ("subscription_status",)
    search_fields = ("name", "phone")
    readonly_fields = ("created_at", "days_remaining")
    fields = (
        "name", "phone", "address", "subscription_status",
        "trial_ends_at", "paid_until", "created_at", "days_remaining",
    )

    @admin.display(description="Days left")
    def days_remaining(self, obj):
        if obj.subscription_status == Clinic.SubscriptionStatus.TRIALING:
            return obj.trial_days_remaining
        if obj.subscription_status == Clinic.SubscriptionStatus.ACTIVE:
            return obj.paid_days_remaining
        return "—"


@admin.register(PaymentSubmission)
class PaymentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "clinic", "amount", "reference", "status",
        "submitted_at", "reviewed_by",
    )
    list_filter = ("status", "submitted_at")
    search_fields = ("clinic__name", "reference")
    readonly_fields = ("submitted_by", "submitted_at", "reviewed_by", "reviewed_at")
    actions = ["approve_payments", "reject_payments"]

    @admin.action(description="✓ Approve — activate clinic for 30 days")
    def approve_payments(self, request, queryset):
        count = 0
        for sub in queryset.filter(status=PaymentSubmission.Status.PENDING):
            sub.approve(reviewed_by=request.user, days=30)
            recipients = [u.email for u in sub.clinic.users.all() if u.email]
            if recipients:
                send_mail(
                    subject="[DocuMed] Your clinic is now active",
                    message=(
                        f"Your payment was verified. {sub.clinic.name} is active "
                        f"until {sub.clinic.paid_until}. Thank you for using DocuMed."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipients,
                    fail_silently=True,
                )
            count += 1
        self.message_user(request, f"{count} payment(s) approved and clinic(s) activated.")

    @admin.action(description="✗ Reject selected payments")
    def reject_payments(self, request, queryset):
        count = 0
        for sub in queryset.filter(status=PaymentSubmission.Status.PENDING):
            sub.reject(reviewed_by=request.user)
            count += 1
        self.message_user(request, f"{count} payment(s) rejected.")


@admin.register(RenewalReminder)
class RenewalReminderAdmin(admin.ModelAdmin):
    list_display = ("clinic", "kind", "days_before", "period_end", "sent_at")
    list_filter = ("kind", "days_before", "sent_at")
    search_fields = ("clinic__name",)
    readonly_fields = ("clinic", "kind", "period_end", "days_before", "sent_at")

    def has_add_permission(self, request):
        return False  # rows are created by the reminder command only
