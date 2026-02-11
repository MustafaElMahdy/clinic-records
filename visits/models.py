from django.conf import settings
from django.db import models
from django.utils import timezone
from clinics.models import Clinic
from clinics.managers import ClinicManager
from patients.models import Patient

User = settings.AUTH_USER_MODEL


class Visit(models.Model):
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        related_name="visits",
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="visits"
    )

    doctor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_visits"
    )

    visit_datetime = models.DateTimeField(default=timezone.now)

    chief_complaint = models.CharField(max_length=255, blank=True)
    clinical_notes = models.TextField(help_text="Free text clinical notes")
    diagnosis = models.CharField(max_length=255, blank=True)
    treatment_plan = models.TextField(blank=True)

    follow_up_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClinicManager()

    def save(self, *args, **kwargs):
        # keep visit.clinic consistent with patient.clinic
        if self.patient_id:
            self.clinic = self.patient.clinic
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Visit {self.id} - {self.patient.full_name}"

    class Meta:
        ordering = ["-visit_datetime"]
        indexes = [
            models.Index(fields=["visit_datetime"]),
            models.Index(fields=["clinic", "visit_datetime"]),
        ]