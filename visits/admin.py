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
    )

    list_filter = ("visit_datetime", "doctor")
    search_fields = (
        "patient__full_name",
        "patient__phone",
        "chief_complaint",
        "diagnosis",
    )

    autocomplete_fields = ("patient", "doctor")
from django.contrib import admin

# Register your models here.
