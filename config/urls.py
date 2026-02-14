from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),

    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Password reset flow
    path("password-reset/",
        auth_views.PasswordResetView.as_view(template_name="registration/password_reset_form.html"),
        name="password_reset"),
    path("password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"),
        name="password_reset_confirm"),
    path("password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete"),

    path("", TemplateView.as_view(template_name="marketing/landing.html"), name="landing"),
    path("privacy/", TemplateView.as_view(template_name="marketing/privacy.html"), name="privacy"),
    path("terms/", TemplateView.as_view(template_name="marketing/terms.html"), name="terms"),

    path("", include("patients.urls")),
    path("visits/", include("visits.urls")),
    path("files/", include("files.urls")),
    path("users/", include("accounts.urls")),
    path("clinic/", include("clinics.urls")),
]

# Media files are intentionally NOT served at /media/ directly.
# All file access must go through files:download (authenticated, clinic-scoped).
