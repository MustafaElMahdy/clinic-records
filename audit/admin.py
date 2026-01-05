from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "object_type", "object_id", "patient_id", "visit_id", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("actor__username", "object_type", "object_id", "patient_id", "visit_id", "ip_address")
    ordering = ("-created_at",)
from django.contrib import admin

# Register your models here.
