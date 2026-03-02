from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Visit

class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["visit_datetime", "chief_complaint", "clinical_notes", "diagnosis", "treatment_plan", "follow_up_date"]
        widgets = {
            "visit_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "visit_datetime": _("Visit Date & Time"),
            "chief_complaint": _("Chief Complaint"),
            "clinical_notes": _("Clinical Notes"),
            "diagnosis": _("Diagnosis"),
            "treatment_plan": _("Treatment Plan"),
            "follow_up_date": _("Follow-up Date"),
        }
