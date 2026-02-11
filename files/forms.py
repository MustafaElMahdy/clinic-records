from django import forms
from .models import Attachment


class AttachmentForm(forms.ModelForm):
    """
    Form for uploading medical documents/files.
    """
    class Meta:
        model = Attachment
        fields = ['file', 'file_type', 'title', 'notes', 'visit']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g., Chest X-Ray - 2024-02-12'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes about this file'}),
            'visit': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, patient=None, clinic=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Limit visit choices to patient's visits only
        if patient:
            self.fields['visit'].queryset = patient.visits.filter(clinic=clinic).order_by('-visit_datetime')
            self.fields['visit'].empty_label = "Not linked to a specific visit"

        # File field configuration
        self.fields['file'].widget.attrs.update({
            'accept': 'image/*,.pdf,.doc,.docx',
            'class': 'form-control'
        })

    def clean_file(self):
        file = self.cleaned_data.get('file')

        if not file:
            raise forms.ValidationError("Please select a file to upload.")

        # File size limit: 10MB
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        if file.size > max_size:
            raise forms.ValidationError(f"File size must be under 10MB. Your file is {file.size / (1024*1024):.1f}MB.")

        # Allowed file extensions
        allowed_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',  # Images
            '.pdf',  # PDFs
            '.doc', '.docx',  # Word documents
        ]

        file_ext = file.name.lower()
        if not any(file_ext.endswith(ext) for ext in allowed_extensions):
            raise forms.ValidationError(
                f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )

        return file
