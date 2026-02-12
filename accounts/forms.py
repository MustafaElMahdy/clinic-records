from django import forms
from .models import User


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        min_length=8,
        help_text="Minimum 8 characters.",
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "role"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make is_active label clearer
        self.fields["is_active"].label = "Account active"
        self.fields["is_active"].help_text = "Uncheck to prevent this user from logging in."
