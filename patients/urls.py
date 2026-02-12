from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    path("", views.patient_list, name="list"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("patients/new/", views.patient_create, name="create"),
    path("patients/<int:pk>/", views.patient_detail, name="detail"),
]
