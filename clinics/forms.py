from django import forms
from .models import Clinic


class ClinicSettingsForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = ["name", "phone", "address"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }
