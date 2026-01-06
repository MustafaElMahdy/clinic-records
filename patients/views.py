import time

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from visits.forms import VisitForm
from visits.models import Visit
from .forms import PatientForm
from .models import Patient


@login_required
@role_required("doctor", "assistant", "admin")
def patient_list(request):
    q = request.GET.get("q", "").strip()

    patients = Patient.objects.all().order_by("full_name")
    if q:
        q_norm = " ".join(q.lower().split())
        patients = patients.filter(
            Q(normalized_name__contains=q_norm)
            | Q(phone__icontains=q)
            | Q(national_id__icontains=q)
        )

    return render(request, "patients/patient_list.html", {"patients": patients, "q": q})


@login_required
@role_required("doctor", "assistant", "admin")
def patient_create(request):
    def normalize_phone(s: str) -> str:
        """Normalize common Egypt phone formats into a comparable string."""
        if not s:
            return ""
        s = s.strip().replace(" ", "").replace("-", "")
        if s.startswith("+20"):
            s = "0" + s[3:]
        elif s.startswith("20") and len(s) >= 12:
            s = "0" + s[2:]
        return s

    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            confirm = request.POST.get("confirm_duplicate") == "1"

            phone = normalize_phone(form.cleaned_data.get("phone") or "")
            national_id = (form.cleaned_data.get("national_id") or "").strip()

            dup_q = Q()
            if national_id:
                dup_q |= Q(national_id__iexact=national_id)
            if phone:
                # This assumes you usually store phone numbers somewhat consistently.
                dup_q |= Q(phone__icontains=phone)

            duplicates = Patient.objects.filter(dup_q).order_by("full_name") if dup_q else Patient.objects.none()

            # If duplicates exist, show warning unless user confirms "create anyway"
            if duplicates.exists() and not confirm:
                return render(
                    request,
                    "patients/duplicate_warning.html",
                    {
                        "form": form,  # keep bound form data
                        "duplicates": duplicates[:10],
                        "submitted_name": form.cleaned_data.get("full_name"),
                        "submitted_phone": form.cleaned_data.get("phone"),
                        "submitted_national_id": national_id,
                    },
                )

            # Create patient
            patient = form.save()

            # Audit log: patient created
            log_event(
                request,
                action=AuditEvent.Action.PATIENT_CREATED,
                obj=patient,
                patient_id=patient.pk,
            )

            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientForm()

    return render(request, "patients/patient_form.html", {"form": form})



@login_required
@role_required("doctor", "assistant", "admin")
def patient_detail(request, pk: int):
    patient = get_object_or_404(Patient, pk=pk)
    visits = Visit.objects.filter(patient=patient).order_by("-visit_datetime")

    # ---- Throttled patient_viewed audit (once per 10 minutes per patient per session) ----
    VIEW_THROTTLE_SECONDS = 10 * 60  # 10 minutes
    session_key = f"audit_patient_viewed_ts_{patient.pk}"

    now_ts = time.time()
    last_ts = request.session.get(session_key)

    should_log_view = (last_ts is None) or ((now_ts - float(last_ts)) >= VIEW_THROTTLE_SECONDS)

    if should_log_view:
        log_event(
            request,
            action=AuditEvent.Action.PATIENT_VIEWED,
            obj=patient,
            patient_id=patient.pk,
        )
        request.session[session_key] = now_ts

    # Doctor-only audit visibility
    can_view_audit = request.user.role in ("doctor", "admin")
    audit_events = []
    if can_view_audit:
        audit_events = (
            AuditEvent.objects
            .filter(patient_id=patient.pk)
            .select_related("actor")
            .order_by("-created_at")[:50]
        )

    can_add_visit = request.user.role in ("doctor", "assistant", "admin")

    if request.method == "POST":
        if not can_add_visit:
            return HttpResponseForbidden("You do not have permission to add visits.")

        visit_form = VisitForm(request.POST)
        if visit_form.is_valid():
            visit = visit_form.save(commit=False)
            visit.patient = patient

            # Only auto-assign doctor if a doctor is logged in
            if request.user.role == "doctor":
                visit.doctor = request.user

            visit.save()

            # Audit log: visit created
            log_event(
                request,
                action=AuditEvent.Action.VISIT_CREATED,
                obj=visit,
                patient_id=patient.pk,
                visit_id=visit.pk,
                metadata={
                    "visit_datetime": visit.visit_datetime.isoformat() if visit.visit_datetime else None,
                    "chief_complaint": visit.chief_complaint,
                },
            )

            return redirect("patients:detail", pk=patient.pk)
    else:
        visit_form = VisitForm()

    return render(
        request,
        "patients/patient_detail.html",
        {
            "patient": patient,
            "visits": visits,
            "visit_form": visit_form,
            "can_add_visit": can_add_visit,
            "can_view_audit": can_view_audit,
            "audit_events": audit_events,
        },
    )
