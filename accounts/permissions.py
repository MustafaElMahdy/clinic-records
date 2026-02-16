from functools import wraps
from django.http import HttpResponseForbidden

def role_required(*allowed_roles: str):
    """
    Usage:
        @role_required("doctor")
        @role_required("doctor", "assistant")
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                # Let @login_required handle redirects in views.
                return HttpResponseForbidden("Not authenticated.")
            if not user.is_superuser and getattr(user, "role", None) not in allowed_roles:
                return HttpResponseForbidden("You do not have permission to perform this action.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
