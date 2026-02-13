from django.urls import path
from . import views

app_name = "clinics"

urlpatterns = [
    path("settings/", views.clinic_settings, name="settings"),
]
