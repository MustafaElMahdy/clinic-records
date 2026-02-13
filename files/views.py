import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from patients.models import Patient
from .forms import AttachmentForm
from .models import Attachment


@login_required
@role_required("doctor", "assistant", "admin")
def attachment_upload(request, patient_pk):
    """
    Upload a new file attachment for a patient.
    """
    # Get patient (scoped to clinic)
    patient = get_object_or_404(Patient.objects.for_clinic(request.clinic), pk=patient_pk)

    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES, patient=patient, clinic=request.clinic)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.clinic = request.clinic
            attachment.patient = patient
            attachment.uploaded_by = request.user

            # Store file metadata
            uploaded_file = request.FILES['file']
            attachment.original_filename = uploaded_file.name
            attachment.file_size = uploaded_file.size
            attachment.mime_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or ''

            attachment.save()

            # Audit log
            log_event(
                request,
                action=AuditEvent.Action.FILE_UPLOADED,
                obj=attachment,
                patient_id=patient.pk,
                metadata={
                    'filename': attachment.original_filename,
                    'file_type': attachment.file_type,
                    'file_size': attachment.file_size,
                }
            )

            messages.success(request, f'File "{attachment.original_filename}" uploaded successfully.')
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = AttachmentForm(patient=patient, clinic=request.clinic)

    return render(request, "files/attachment_upload.html", {
        "form": form,
        "patient": patient,
    })


@login_required
@role_required("doctor", "assistant", "admin")
def attachment_download(request, pk):
    """
    Download/view a file attachment.
    """
    # Get attachment (scoped to clinic)
    attachment = get_object_or_404(Attachment.objects.for_clinic(request.clinic), pk=pk)

    # Verify file exists
    if not attachment.file:
        raise Http404("File not found")

    # Audit log
    log_event(
        request,
        action=AuditEvent.Action.FILE_DOWNLOADED,
        obj=attachment,
        patient_id=attachment.patient_id,
        metadata={
            'filename': attachment.original_filename,
        }
    )

    # Serve file
    file_handle = attachment.file.open('rb')

    # Determine if we should display inline (images, PDFs) or force download
    content_disposition = 'inline' if (attachment.is_image() or attachment.is_pdf()) else 'attachment'

    response = FileResponse(
        file_handle,
        content_type=attachment.mime_type or 'application/octet-stream'
    )
    response['Content-Disposition'] = f'{content_disposition}; filename="{attachment.original_filename}"'

    return response


@login_required
@role_required("doctor", "admin")  # Only doctors and admins can delete files
def attachment_delete(request, pk):
    """
    Delete a file attachment.
    """
    # Get attachment (scoped to clinic)
    attachment = get_object_or_404(Attachment.objects.for_clinic(request.clinic), pk=pk)
    patient_pk = attachment.patient.pk

    if request.method == "POST":
        # Store metadata before deletion
        filename = attachment.original_filename
        file_type = attachment.file_type

        # Delete the physical file
        if attachment.file:
            attachment.file.delete(save=False)

        # Audit log before deleting the object
        log_event(
            request,
            action=AuditEvent.Action.FILE_DELETED,
            obj=attachment,
            patient_id=attachment.patient_id,
            metadata={
                'filename': filename,
                'file_type': file_type,
            }
        )

        # Delete the database record
        attachment.delete()

        messages.success(request, f'File "{filename}" deleted.')
        return redirect("patients:detail", pk=patient_pk)

    return render(request, "files/attachment_delete_confirm.html", {
        "attachment": attachment,
        "patient": attachment.patient,
    })
