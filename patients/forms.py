from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["full_name", "phone", "national_id", "sex", "date_of_birth", "address", "notes"]
        labels = {
            "full_name": _("Full Name"),
            "phone": _("Phone"),
            "national_id": _("National ID"),
            "sex": _("Sex"),
            "date_of_birth": _("Date of Birth"),
            "address": _("Address"),
            "notes": _("Notes"),
        }
