from .models import AuditEvent


def get_client_ip(request):
    # simple dev-friendly version
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(request, *, action, obj, patient_id=None, visit_id=None, metadata=None):
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None

    AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=f"{obj.__class__.__module__}.{obj.__class__.__name__}",
        object_id=obj.pk,
        patient_id=patient_id,
        visit_id=visit_id,
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        metadata=metadata or {},
    )
