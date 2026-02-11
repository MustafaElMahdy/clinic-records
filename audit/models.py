from django.conf import settings
from django.db import models
from clinics.models import Clinic
from clinics.managers import ClinicManager


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        PATIENT_CREATED = "patient_created", "Patient created"
        VISIT_CREATED = "visit_created", "Visit created"
        VISIT_EDITED = "visit_edited", "Visit edited"
        PATIENT_VIEWED = "patient_viewed", "Patient viewed"
        FILE_UPLOADED = "file_uploaded", "File uploaded"
        FILE_DOWNLOADED = "file_downloaded", "File downloaded"
        FILE_DELETED = "file_deleted", "File deleted"

    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ tenant / clinic scoping
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )   

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    action = models.CharField(max_length=50, choices=Action.choices)

    object_type = models.CharField(max_length=50)   # e.g. "patients.Patient"
    object_id = models.PositiveIntegerField()       # e.g. pk of the object

    patient_id = models.PositiveIntegerField(null=True, blank=True)
    visit_id = models.PositiveIntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)
    display = models.CharField(max_length=255, blank=True, default="")

    objects = ClinicManager()

    def __str__(self):
        return f"{self.created_at} - {self.action} - {self.object_type}:{self.object_id}"