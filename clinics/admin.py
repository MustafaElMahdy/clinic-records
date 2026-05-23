from django.contrib import admin
from .models import Clinic


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "subscription_status", "trial_ends_at", "days_remaining", "phone", "created_at")
    list_filter = ("subscription_status",)
    search_fields = ("name", "phone")
    readonly_fields = ("created_at", "days_remaining")
    fields = ("name", "phone", "address", "subscription_status", "trial_ends_at", "created_at", "days_remaining")

    @admin.display(description="Days left")
    def days_remaining(self, obj):
        return obj.trial_days_remaining if obj.subscription_status == Clinic.SubscriptionStatus.TRIALING else "—"