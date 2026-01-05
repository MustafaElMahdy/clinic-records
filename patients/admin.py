from django.contrib import admin
from .models import Patient

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "national_id", "sex", "date_of_birth")
    search_fields = ("full_name", "normalized_name", "phone", "national_id")
    list_filter = ("sex",)
from django.contrib import admin

# Register your models here.
