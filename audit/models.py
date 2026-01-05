from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        PATIENT_CREATED = "patient_created", "Patient created"
        VISIT_CREATED = "visit_created", "Visit created"
        VISIT_EDITED = "visit_edited", "Visit edited"
        PATIENT_VIEWED = "patient_viewed", "Patient viewed"

    created_at = models.DateTimeField(auto_now_add=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    action = models.CharField(max_length=50, choices=Action.choices)

    # Generic object reference (so it works for Patient, Visit, etc.)
    object_type = models.CharField(max_length=50)   # e.g. "patients.Patient"
    object_id = models.PositiveIntegerField()       # e.g. pk of the object

    # Useful context
    patient_id = models.PositiveIntegerField(null=True, blank=True)
    visit_id = models.PositiveIntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)
    display = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return f"{self.created_at} - {self.action} - {self.object_type}:{self.object_id}"
from django.db import models

# Create your models here.
