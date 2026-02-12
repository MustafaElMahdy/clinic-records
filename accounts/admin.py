from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Clinic & Role", {"fields": ("clinic", "role")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Clinic & Role", {"fields": ("clinic", "role")}),
    )

    list_display = ("username", "email", "clinic", "role", "is_staff", "is_active")
    list_filter = ("clinic", "role", "is_staff", "is_active")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user has a clinic, filter by that clinic
        if hasattr(request.user, 'clinic') and request.user.clinic:
            return qs.filter(clinic=request.user.clinic)
        return qs