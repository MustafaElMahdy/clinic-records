from django import forms
from accounts.models import User
from .models import Clinic


class ClinicSettingsForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = ["name", "phone", "address"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class ClinicSignupForm(forms.Form):
    clinic_name = forms.CharField(max_length=200, label="Clinic name")
    first_name = forms.CharField(max_length=150, label="Your first name")
    last_name = forms.CharField(max_length=150, label="Your last name")
    email = forms.EmailField(label="Email address")
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        min_length=8,
        label="Password",
        help_text="Minimum 8 characters.",
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Confirm password",
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned_data
