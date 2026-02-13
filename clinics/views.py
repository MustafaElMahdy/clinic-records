from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
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
