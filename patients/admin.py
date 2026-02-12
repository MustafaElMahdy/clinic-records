from django.contrib import admin
from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "national_id", "sex", "date_of_birth", "clinic")
    search_fields = ("full_name", "normalized_name", "phone", "national_id")
    list_filter = ("sex", "clinic")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user has a clinic, filter by that clinic
        if hasattr(request.user, 'clinic') and request.user.clinic:
            return qs.filter(clinic=request.user.clinic)
        return qs
