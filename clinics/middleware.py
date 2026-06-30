# clinics/middleware.py
from django.shortcuts import redirect
from django.urls import reverse


class ClinicMiddleware:
    EXEMPT_PREFIXES = (
        "/login/",
        "/logout/",
        "/signup/",
        "/clinic/subscription/",
        "/admin/",
        "/static/",
        "/media/",
        "/privacy/",
        "/terms/",
        "/password-reset/",
        "/set-language/",
        "/track/",
    )
    EXEMPT_PATHS = {"/"}  # exact matches

    TRIAL_WARNING_DAYS = 3

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Allow unauthenticated users and exempt paths
        if (not getattr(request, "user", None) or not request.user.is_authenticated
            or path in self.EXEMPT_PATHS
            or path.startswith(self.EXEMPT_PREFIXES)):
            return self.get_response(request)

        # Attach clinic to request (may be None for superusers)
        request.clinic = getattr(request.user, "clinic", None)

        # Superusers can proceed without a clinic
        if request.user.is_superuser:
            return self.get_response(request)

        # If user has no clinic, log them out and redirect to login
        if request.clinic is None:
            from django.contrib.auth import logout
            logout(request)
            return redirect(reverse("login") + "?no_clinic=1")

        # Block access if trial expired or subscription lapsed
        if not request.clinic.is_access_allowed:
            return redirect(reverse("clinics:subscription"))

        # Warn when trial is almost over
        days = request.clinic.trial_days_remaining
        request.trial_days_remaining = days if 0 < days <= self.TRIAL_WARNING_DAYS else None

        return self.get_response(request)