from django.urls import path
from . import views

app_name = "visits"

urlpatterns = [
    path("<int:pk>/edit/", views.visit_edit, name="edit"),
]
