from django.contrib import admin
from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'patient', 'clinic', 'file_type', 'uploaded_by', 'uploaded_at', 'get_file_size_display']
    list_filter = ['clinic', 'file_type', 'uploaded_at']
    search_fields = ['original_filename', 'patient__full_name', 'title']
    readonly_fields = ['uploaded_at', 'file_size', 'mime_type', 'original_filename']

    fieldsets = (
        ('File Information', {
            'fields': ('file', 'original_filename', 'file_type', 'mime_type', 'file_size')
        }),
        ('Associations', {
            'fields': ('clinic', 'patient', 'visit', 'uploaded_by')
        }),
        ('Details', {
            'fields': ('title', 'notes', 'uploaded_at')
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user has a clinic, filter by that clinic
        if hasattr(request.user, 'clinic') and request.user.clinic:
            return qs.filter(clinic=request.user.clinic)
        return qs
