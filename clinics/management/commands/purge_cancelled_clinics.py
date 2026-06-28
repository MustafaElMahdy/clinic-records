"""
Permanently delete data for clinics whose access ended more than N days ago
(default 90), honoring the retention promise in the Privacy Policy & Terms.

SAFETY:
- Dry-run by default. Pass --commit to actually delete.
- Only targets clinics that are NOT currently allowed access AND whose most
  recent access-end date (paid_until / trial_ends_at) is older than the cutoff.
- Skips clinics with no end date on record (can't determine when access ended).
- Each clinic is deleted in its own transaction, children first (the clinic FK
  is PROTECT on users/patients/visits/attachments/audit events).

Schedule on Render as a weekly Cron Job:
    python manage.py purge_cancelled_clinics --commit
"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.models import AuditEvent
from clinics.models import Clinic, PaymentSubmission, RenewalReminder
from files.models import Attachment
from patients.models import Patient
from visits.models import Visit

RETENTION_DAYS = 90


class Command(BaseCommand):
    help = "Permanently delete data for clinics cancelled/expired beyond the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true",
            help="Actually delete. Without this flag the command only reports (dry-run).",
        )
        parser.add_argument(
            "--days", type=int, default=RETENTION_DAYS,
            help=f"Retention window in days (default {RETENTION_DAYS}).",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        days = options["days"]
        today = timezone.now().date()
        cutoff = today - timedelta(days=days)

        eligible = []
        for clinic in Clinic.objects.all():
            if clinic.is_access_allowed:
                continue  # active or still in trial — never purge
            ends = [d for d in (clinic.paid_until, clinic.trial_ends_at) if d]
            if not ends:
                continue  # no end date on record — skip for safety
            access_ended = max(ends)
            if access_ended < cutoff:
                eligible.append((clinic, access_ended))

        if not eligible:
            self.stdout.write(self.style.SUCCESS("No clinics past the retention window."))
            return

        lines = []
        for clinic, access_ended in eligible:
            counts = {
                "patients": Patient.objects.filter(clinic=clinic).count(),
                "visits": Visit.objects.filter(clinic=clinic).count(),
                "attachments": Attachment.objects.filter(clinic=clinic).count(),
                "users": User.objects.filter(clinic=clinic).count(),
            }
            line = (f"{clinic.name} (id={clinic.id}) — access ended {access_ended} — "
                    f"{counts['patients']} patients, {counts['visits']} visits, "
                    f"{counts['attachments']} files, {counts['users']} users")
            lines.append(line)

            if commit:
                self._purge(clinic)
                self.stdout.write(self.style.WARNING(f"DELETED: {line}"))
            else:
                self.stdout.write(f"[dry-run] would delete: {line}")

        verb = "Deleted" if commit else "Would delete"
        summary = f"{verb} {len(eligible)} clinic(s) past the {days}-day retention window."
        self.stdout.write(self.style.SUCCESS(summary))

        # Notify the owner for oversight (only on real deletions).
        if commit:
            send_mail(
                subject=f"[DocuMed] Retention purge: {len(eligible)} clinic(s) deleted",
                message=summary + "\n\n" + "\n".join(lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.PAYMENT_NOTIFICATION_EMAIL],
                fail_silently=True,
            )

    def _purge(self, clinic):
        """Delete all of a clinic's data, children before the clinic itself."""
        with transaction.atomic():
            # Remove attachment blobs from object storage (R2), then the rows.
            for att in Attachment.objects.filter(clinic=clinic):
                if att.file:
                    att.file.delete(save=False)
            Attachment.objects.filter(clinic=clinic).delete()
            Visit.objects.filter(clinic=clinic).delete()
            Patient.objects.filter(clinic=clinic).delete()
            AuditEvent.objects.filter(clinic=clinic).delete()
            PaymentSubmission.objects.filter(clinic=clinic).delete()
            RenewalReminder.objects.filter(clinic=clinic).delete()
            # Users reference clinic via PROTECT; their SET_NULL back-references
            # (visit.doctor, audit.actor, uploaded_by, etc.) are already gone.
            User.objects.filter(clinic=clinic).delete()
            clinic.delete()
