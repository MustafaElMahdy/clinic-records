# clinics/middleware.py
from django.shortcuts import redirect
from django.urls import reverse


class ClinicMiddleware:
    """
    Middleware that attaches the user's clinic to the request object.

    For authenticated users without a clinic, they are logged out and redirected
    to the login page with a query parameter indicating the reason.

    Exempt paths (login, logout, admin, static, media) are not affected.
    """
    EXEMPT_PREFIXES = (
        "/login/",
        "/logout/",
        "/admin/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Allow unauthenticated users + exempt paths
        if (not getattr(request, "user", None) or not request.user.is_authenticated
            or path.startswith(self.EXEMPT_PREFIXES)):
            return self.get_response(request)

        # Attach clinic to request
        request.clinic = getattr(request.user, "clinic", None)

        # If user has no clinic, log them out and redirect to login
        if request.clinic is None:
            from django.contrib.auth import logout
            logout(request)
            return redirect(reverse("login") + "?no_clinic=1")

        return self.get_response(request)