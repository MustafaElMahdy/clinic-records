import os
from django.conf import settings
from django.db import models
from django.utils import timezone
from clinics.models import Clinic
from clinics.managers import ClinicManager
from patients.models import Patient
from visits.models import Visit


def attachment_upload_path(instance, filename):
    """
    Generate upload path: media/clinic_{id}/patient_{id}/filename
    """
    clinic_id = instance.clinic.pk
    patient_id = instance.patient.pk
    # Sanitize filename
    name, ext = os.path.splitext(filename)
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    return f'clinic_{clinic_id}/patient_{patient_id}/{safe_name}{ext}'


class Attachment(models.Model):
    """
    Medical documents, x-rays, lab reports, etc. attached to patients.
    """
    class FileType(models.TextChoices):
        XRAY = 'xray', 'X-Ray'
        LAB_RESULT = 'lab', 'Lab Result'
        PRESCRIPTION = 'prescription', 'Prescription'
        REPORT = 'report', 'Medical Report'
        OTHER = 'other', 'Other'

    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        related_name='attachments',
    )

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='attachments',
    )

    visit = models.ForeignKey(
        Visit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attachments',
        help_text="Optional: Link to a specific visit"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_files',
    )

    file = models.FileField(upload_to=attachment_upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        default=FileType.OTHER
    )
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)

    title = models.CharField(max_length=255, blank=True, help_text="Optional description")
    notes = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(default=timezone.now)

    objects = ClinicManager()

    def __str__(self):
        return f"{self.original_filename} - {self.patient.full_name}"

    def get_file_extension(self):
        """Return file extension in lowercase"""
        return os.path.splitext(self.original_filename)[1].lower()

    def is_image(self):
        """Check if file is an image"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        return self.get_file_extension() in image_extensions

    def is_pdf(self):
        """Check if file is a PDF"""
        return self.get_file_extension() == '.pdf'

    def get_file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['clinic', 'patient']),
            models.Index(fields=['clinic', 'uploaded_at']),
            models.Index(fields=['patient', '-uploaded_at']),
        ]
