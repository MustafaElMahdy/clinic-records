from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "object_type", "object_id", "patient_id", "visit_id", "clinic", "ip_address")
    list_filter = ("action", "created_at", "clinic")
    search_fields = ("actor__username", "object_type", "object_id", "patient_id", "visit_id", "ip_address")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user has a clinic, filter by that clinic
        if hasattr(request.user, 'clinic') and request.user.clinic:
            return qs.filter(clinic=request.user.clinic)
        return qs
