import time
from datetime import timedelta
from django.utils import timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from files.models import Attachment
from visits.forms import VisitForm
from visits.models import Visit
from .forms import PatientForm
from .models import Patient


@login_required
@role_required("admin")
def admin_dashboard(request):
    """Admin dashboard showing clinic statistics and management tools."""
    clinic = request.clinic

    # Get statistics
    total_patients = Patient.objects.for_clinic(clinic).count()
    total_visits = Visit.objects.for_clinic(clinic).count()
    total_files = Attachment.objects.for_clinic(clinic).count()

    # Recent activity (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_patients = Patient.objects.for_clinic(clinic).filter(created_at__gte=thirty_days_ago).count()
    recent_visits = Visit.objects.for_clinic(clinic).filter(visit_datetime__gte=thirty_days_ago).count()

    # User statistics
    users = User.objects.filter(clinic=clinic).select_related('clinic')
    total_users = users.count()
    users_by_role = users.values('role').annotate(count=Count('id')).order_by('role')

    # Recent audit events
    recent_audit = (
        AuditEvent.objects
        .for_clinic(clinic)
        .select_related('actor')
        .order_by('-created_at')[:20]
    )

    context = {
        'clinic': clinic,
        'total_patients': total_patients,
        'total_visits': total_visits,
        'total_files': total_files,
        'recent_patients': recent_patients,
        'recent_visits': recent_visits,
        'total_users': total_users,
        'users_by_role': users_by_role,
        'recent_audit': recent_audit,
        'users': users,
    }

    return render(request, 'admin/dashboard.html', context)


@login_required
@role_required("doctor", "assistant", "admin")
def patient_list(request):
    q = request.GET.get("q", "").strip()

    # ✅ scope by clinic
    patients = Patient.objects.for_clinic(request.clinic).order_by("full_name")

    if q:
        q_norm = " ".join(q.lower().split())
        patients = patients.filter(
            Q(normalized_name__contains=q_norm)
            | Q(phone__icontains=q)
            | Q(national_id__icontains=q)
        )

    paginator = Paginator(patients, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "patients/patient_list.html", {"page_obj": page_obj, "q": q})


@login_required
@role_required("doctor", "assistant", "admin")
def patient_create(request):
    def normalize_phone(s: str) -> str:
        """Normalize common Egypt phone formats into comparable string."""
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

            input_phone_raw = form.cleaned_data.get("phone") or ""
            input_phone = normalize_phone(input_phone_raw)
            national_id = (form.cleaned_data.get("national_id") or "").strip()

            matched_ids = []
            match_reasons = {}  # patient_id -> ["national_id", "phone"]

            # ✅ scope duplicate search by clinic
            if national_id or input_phone:
                candidates = (
                    Patient.objects
                    .for_clinic(request.clinic)
                    .only("id", "full_name", "phone", "national_id")
                )

                for p in candidates:
                    reasons = []

                    # Strong match: national ID
                    if national_id and p.national_id and p.national_id.strip().lower() == national_id.lower():
                        reasons.append("national_id")

                    # Soft match: phone (normalized)
                    if input_phone and p.phone:
                        stored_phone = normalize_phone(p.phone)
                        if stored_phone and stored_phone == input_phone:
                            reasons.append("phone")

                    if reasons:
                        matched_ids.append(p.id)
                        match_reasons[p.id] = reasons

            duplicates = (
                Patient.objects.for_clinic(request.clinic).filter(id__in=matched_ids).order_by("full_name")
                if matched_ids
                else Patient.objects.none()
            )

            if duplicates.exists() and not confirm:
                return render(
                    request,
                    "patients/duplicate_warning.html",
                    {
                        "form": form,
                        "duplicates": duplicates[:10],
                        "match_reasons": match_reasons,
                        "submitted_name": form.cleaned_data.get("full_name"),
                        "submitted_phone": input_phone_raw,
                        "submitted_national_id": national_id,
                    },
                )

            # ✅ create patient and assign clinic
            patient = form.save(commit=False)
            patient.clinic = request.clinic

            try:
                patient.save()
            except IntegrityError as e:
                # Handle uniqueness constraint violations
                error_msg = str(e).lower()

                # Check which field caused the violation
                if 'unique_national_id_per_clinic' in error_msg or ('national_id' in error_msg and 'unique' in error_msg):
                    form.add_error('national_id',
                        'A patient with this National ID already exists in your clinic.')
                elif 'unique_phone_per_clinic' in error_msg or ('phone' in error_msg and 'unique' in error_msg):
                    form.add_error('phone',
                        'A patient with this phone number already exists in your clinic.')
                else:
                    form.add_error(None,
                        'A patient with these details already exists in your clinic.')

                return render(request, "patients/patient_form.html", {"form": form})

            log_event(
                request,
                action=AuditEvent.Action.PATIENT_CREATED,
                obj=patient,
                patient_id=patient.pk,
            )

            messages.success(request, f'Patient "{patient.full_name}" created successfully.')
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientForm()

    return render(request, "patients/patient_form.html", {"form": form, "is_edit": False})


@login_required
@role_required("doctor", "admin")
def patient_edit(request, pk: int):
    patient = get_object_or_404(Patient.objects.for_clinic(request.clinic), pk=pk)

    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError as e:
                error_msg = str(e).lower()
                if "unique_national_id_per_clinic" in error_msg or ("national_id" in error_msg and "unique" in error_msg):
                    form.add_error("national_id", "A patient with this National ID already exists in your clinic.")
                elif "unique_phone_per_clinic" in error_msg or ("phone" in error_msg and "unique" in error_msg):
                    form.add_error("phone", "A patient with this phone number already exists in your clinic.")
                else:
                    form.add_error(None, "A patient with these details already exists in your clinic.")
                return render(request, "patients/patient_form.html", {"form": form, "is_edit": True, "patient": patient})

            log_event(
                request,
                action=AuditEvent.Action.PATIENT_EDITED,
                obj=patient,
                patient_id=patient.pk,
            )
            messages.success(request, f'Patient "{patient.full_name}" updated successfully.')
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)

    return render(request, "patients/patient_form.html", {"form": form, "is_edit": True, "patient": patient})


@login_required
@role_required("doctor", "assistant", "admin")
def patient_detail(request, pk: int):
    # ✅ patient must belong to the user's clinic
    patient = get_object_or_404(Patient.objects.for_clinic(request.clinic), pk=pk)

    # ✅ scope visits by clinic too
    visits = Visit.objects.for_clinic(request.clinic).filter(patient=patient).order_by("-visit_datetime")

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

    can_view_audit = request.user.role in ("doctor", "admin")
    audit_events = []
    if can_view_audit:
        # ✅ scope audit by clinic
        audit_events = (
            AuditEvent.objects
            .for_clinic(request.clinic)
            .filter(patient_id=patient.pk)
            .select_related("actor")
            .order_by("-created_at")[:50]
        )

    # ✅ Get attachments for this patient (scoped to clinic)
    attachments = Attachment.objects.for_clinic(request.clinic).filter(patient=patient).order_by("-uploaded_at")

    can_add_visit = request.user.role in ("doctor", "assistant", "admin")

    if request.method == "POST":
        if not can_add_visit:
            return HttpResponseForbidden("You do not have permission to add visits.")

        visit_form = VisitForm(request.POST)
        if visit_form.is_valid():
            visit = visit_form.save(commit=False)
            visit.patient = patient

            # ✅ set clinic explicitly (even if Visit.save() also enforces it)
            visit.clinic = request.clinic

            if request.user.role == "doctor":
                visit.doctor = request.user

            visit.save()

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

            messages.success(request, "Visit added successfully.")
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
            "attachments": attachments,
        },
    )