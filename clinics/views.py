import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

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

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    safe_name = clinic.name.replace(" ", "_")
    filename = f"{safe_name}_export_{date.today()}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # UTF-8 BOM so Excel opens Arabic text correctly
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Patient ID", "Full Name", "Phone", "National ID", "Sex",
        "Date of Birth", "Address", "Notes", "Patient Created",
        "Visit Date", "Chief Complaint", "Clinical Notes",
        "Diagnosis", "Treatment Plan", "Follow-up Date", "Doctor",
    ])

    for patient in patients:
        visits = patient.visits.all()
        if visits:
            for visit in visits:
                writer.writerow([
                    patient.pk, patient.full_name, patient.phone,
                    patient.national_id, patient.get_sex_display(),
                    patient.date_of_birth or "", patient.address, patient.notes,
                    patient.created_at.date(),
                    visit.visit_datetime.date(), visit.chief_complaint,
                    visit.clinical_notes, visit.diagnosis,
                    visit.treatment_plan, visit.follow_up_date or "",
                    visit.doctor.get_full_name() if visit.doctor else "",
                ])
        else:
            writer.writerow([
                patient.pk, patient.full_name, patient.phone,
                patient.national_id, patient.get_sex_display(),
                patient.date_of_birth or "", patient.address, patient.notes,
                patient.created_at.date(),
                "", "", "", "", "", "", "",
            ])

    log_event(
        request,
        action=AuditEvent.Action.DATA_EXPORTED,
        obj=clinic,
        metadata={"patients": patients.count()},
    )

    return response
