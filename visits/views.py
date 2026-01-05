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
    visit = get_object_or_404(Visit, pk=pk)

    if request.method == "POST":
        form = VisitForm(request.POST, instance=visit)
        if form.is_valid():
            updated_visit = form.save()

            # Audit log: visit edited
            log_event(
                request,
                action=AuditEvent.Action.VISIT_EDITED,
                obj=updated_visit,
                patient_id=updated_visit.patient_id,
                visit_id=updated_visit.pk,
                metadata={
                    "visit_datetime": updated_visit.visit_datetime.isoformat() if updated_visit.visit_datetime else None,
                    "chief_complaint": updated_visit.chief_complaint,
                },
            )
            return redirect("patients:detail", pk=updated_visit.patient.pk)
    else:
        form = VisitForm(instance=visit)

    return render(
        request,
        "visits/visit_edit.html",
        {"form": form, "visit": visit},
    )
