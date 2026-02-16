from django.db import models
from django.utils import timezone
from clinics.models import Clinic
from clinics.managers import ClinicManager


def normalize_name(name: str) -> str:
    return " ".join(name.lower().split()) if name else ""


class Patient(models.Model):
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        related_name="patients",
    )
    full_name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, editable=False, db_index=True)

    phone = models.CharField(max_length=30, blank=True, db_index=True)
    national_id = models.CharField(max_length=30, blank=True, db_index=True)

    sex = models.CharField(
        max_length=10,
        choices=(("M", "Male"), ("F", "Female"), ("U", "Unknown")),
        default="U",
    )
    date_of_birth = models.DateField(null=True, blank=True)

    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClinicManager()

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_name(self.full_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["normalized_name"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["national_id"]),
            models.Index(fields=["clinic", "phone"]),
            models.Index(fields=["clinic", "national_id"]),
            models.Index(fields=["clinic", "normalized_name"]),
        ]
        constraints = [
            # Ensure national_id is unique within each clinic (when provided)
            models.UniqueConstraint(
                fields=['clinic', 'national_id'],
                name='unique_national_id_per_clinic',
                condition=models.Q(national_id__isnull=False) & ~models.Q(national_id='')
            ),
        ]