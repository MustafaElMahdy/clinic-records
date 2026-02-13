from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from .forms import VisitForm
from .models import Visit


@login_required
@role_required("doctor", "admin")
def visit_edit(request, pk: int):
    # ✅ BLOCK cross-clinic access immediately
    visit = get_object_or_404(Visit.objects.for_clinic(request.clinic), pk=pk)

    if request.method == "POST":
        form = VisitForm(request.POST, instance=visit)
        if form.is_valid():
            visit = form.save()

            # ✅ audit (also clinic-safe if your log_event sets clinic)
            log_event(
                request,
                action=AuditEvent.Action.VISIT_EDITED,
                obj=visit,
                patient_id=visit.patient_id,
                visit_id=visit.pk,
            )

            messages.success(request, "Visit saved successfully.")
            return redirect("patients:detail", pk=visit.patient.pk)
    else:
        form = VisitForm(instance=visit)

    return render(request, "visits/visit_edit.html", {"form": form, "visit": visit})