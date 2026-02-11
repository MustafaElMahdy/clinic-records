from django.db import models


class ClinicQuerySet(models.QuerySet):
    """
    Custom QuerySet for models that have a clinic foreign key.
    Provides clinic-scoped filtering methods.
    """
    def for_clinic(self, clinic):
        """
        Filter queryset to only include objects from the specified clinic.

        Usage:
            Patient.objects.for_clinic(request.clinic)
        """
        return self.filter(clinic=clinic)


class ClinicManager(models.Manager):
    """
    Custom manager for models with clinic scoping.

    Provides clean methods for filtering by clinic to avoid repetitive
    .filter(clinic=...) throughout the codebase.

    Usage in models:
        class Patient(models.Model):
            clinic = models.ForeignKey(Clinic, ...)
            objects = ClinicManager()

    Usage in views:
        patients = Patient.objects.for_clinic(request.clinic)
    """
    def get_queryset(self):
        return ClinicQuerySet(self.model, using=self._db)

    def for_clinic(self, clinic):
        """
        Return all objects for the specified clinic.

        Args:
            clinic: Clinic instance or clinic ID

        Returns:
            QuerySet filtered by clinic
        """
        return self.get_queryset().for_clinic(clinic)
