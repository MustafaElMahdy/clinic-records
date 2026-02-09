from .models import AuditEvent


def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(request, *, action, obj, patient_id=None, visit_id=None, metadata=None):
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None

    clinic = None

    # 1) Prefer object's clinic if it exists
    if hasattr(obj, "clinic_id"):
        clinic = getattr(obj, "clinic", None)

    # 2) If not, resolve via patient_id or visit_id
    if clinic is None and patient_id:
        from patients.models import Patient
        clinic_id = Patient.objects.filter(pk=patient_id).values_list("clinic_id", flat=True).first()
        if clinic_id:
            from clinics.models import Clinic
            clinic = Clinic.objects.get(pk=clinic_id)

    if clinic is None and visit_id:
        from visits.models import Visit
        clinic = Visit.objects.filter(pk=visit_id).values_list("clinic", flat=True).first()

    # 3) Fallback to user's clinic
    if clinic is None and actor is not None:
        clinic = getattr(actor, "clinic", None)

    AuditEvent.objects.create(
        clinic=clinic if hasattr(clinic, "pk") else None,
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