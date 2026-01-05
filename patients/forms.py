from django import forms
from .models import Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["full_name", "phone", "national_id", "sex", "date_of_birth", "address", "notes"]
