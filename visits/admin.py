from django.contrib import admin
from .models import Visit


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "visit_datetime",
        "doctor",
        "chief_complaint",
        "follow_up_date",
        "clinic",
    )

    list_filter = ("visit_datetime", "doctor", "clinic")
    search_fields = (
        "patient__full_name",
        "patient__phone",
        "chief_complaint",
        "diagnosis",
    )

    autocomplete_fields = ("patient", "doctor")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user has a clinic, filter by that clinic
        if hasattr(request.user, 'clinic') and request.user.clinic:
            return qs.filter(clinic=request.user.clinic)
        return qs
