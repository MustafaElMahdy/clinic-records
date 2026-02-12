from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.user_list, name="list"),
    path("new/", views.user_create, name="create"),
    path("<int:pk>/edit/", views.user_edit, name="edit"),
    path("<int:pk>/toggle-active/", views.user_toggle_active, name="toggle_active"),
]
