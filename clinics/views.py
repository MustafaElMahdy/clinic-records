from datetime import date
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from openpyxl import Workbook

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from patients.models import Patient
from .forms import ClinicSettingsForm


@login_required
@role_required("admin")
def clinic_settings(request):
    clinic = request.clinic

    if request.method == "POST":
        form = ClinicSettingsForm(request.POST, instance=clinic)
        if form.is_valid():
            form.save()
            log_event(
                request,
                action=AuditEvent.Action.CLINIC_UPDATED,
                obj=clinic,
                metadata={
                    "name": clinic.name,
                    "phone": clinic.phone,
                    "address": clinic.address,
                },
            )
            messages.success(request, "Clinic settings saved.")
            return redirect("clinics:settings")
    else:
        form = ClinicSettingsForm(instance=clinic)

    return render(request, "clinics/settings.html", {"form": form, "clinic": clinic})


@login_required
@role_required("admin")
def export_data(request):
    clinic = request.clinic
    patients = (
        Patient.objects.filter(clinic=clinic)
        .prefetch_related("visits__doctor")
        .order_by("full_name")
    )

    wb = Workbook()

    # ── Patients sheet ──
    ws_patients = wb.active
    ws_patients.title = "Patients"
    ws_patients.append([
        "Patient ID", "Full Name", "Phone", "National ID", "Sex",
        "Date of Birth", "Address", "Notes", "Created",
    ])
    for p in patients:
        ws_patients.append([
            p.pk, p.full_name, p.phone, p.national_id, p.get_sex_display(),
            str(p.date_of_birth) if p.date_of_birth else "",
            p.address, p.notes, str(p.created_at.date()),
        ])

    # ── Visits sheet ──
    ws_visits = wb.create_sheet("Visits")
    ws_visits.append([
        "Patient ID", "Patient Name", "Visit Date", "Chief Complaint",
        "Clinical Notes", "Diagnosis", "Treatment Plan",
        "Follow-up Date", "Doctor",
    ])
    for p in patients:
        for visit in p.visits.all():
            ws_visits.append([
                p.pk, p.full_name,
                str(visit.visit_datetime.date()),
                visit.chief_complaint, visit.clinical_notes,
                visit.diagnosis, visit.treatment_plan,
                str(visit.follow_up_date) if visit.follow_up_date else "",
                visit.doctor.get_full_name() if visit.doctor else "",
            ])

    # Write to response
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = clinic.name.replace(" ", "_")
    filename = f"{safe_name}_export_{date.today()}.xlsx"

    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    log_event(
        request,
        action=AuditEvent.Action.DATA_EXPORTED,
        obj=clinic,
        metadata={"patients": patients.count()},
    )

    return response
