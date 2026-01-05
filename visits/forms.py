from django import forms
from .models import Visit

class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["visit_datetime", "chief_complaint", "clinical_notes", "diagnosis", "treatment_plan", "follow_up_date"]
        widgets = {
            "visit_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
        }
