"""
Email clinics before their access ends so they renew via InstaPay.

Sends two reminders per period: 3 days before, and on the day access ends.
Covers both paid subscriptions (paid_until) and free trials (trial_ends_at).
Idempotent via the RenewalReminder table, so it's safe to run daily (or twice).

Schedule on Render as a daily Cron Job:
    python manage.py send_renewal_reminders
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from clinics.models import Clinic, PaymentSubmission, RenewalReminder

OFFSETS = (3, 0)  # days before period_end


class Command(BaseCommand):
    help = "Email clinics 3 days before, and on the day, their access ends."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be sent without sending or recording anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = timezone.now().date()
        max_offset = max(OFFSETS)
        link = settings.SITE_URL.rstrip("/") + reverse("clinics:subscription")
        price = settings.MONTHLY_PRICE_EGP
        instapay = settings.INSTAPAY_ADDRESS

        sent = 0
        skipped = 0

        # Clinics whose trial or paid window ends within the largest offset.
        candidates = Clinic.objects.filter(
            subscription_status__in=[
                Clinic.SubscriptionStatus.TRIALING,
                Clinic.SubscriptionStatus.ACTIVE,
            ]
        )

        for clinic in candidates:
            kind, period_end = self._period(clinic)
            if period_end is None:
                continue
            days_left = (period_end - today).days
            if days_left not in OFFSETS:
                continue

            # They've already paid and are awaiting your approval -> don't nag.
            if kind == RenewalReminder.Kind.PAID and clinic.payment_submissions.filter(
                status=PaymentSubmission.Status.PENDING
            ).exists():
                skipped += 1
                continue

            # Already reminded for this exact period + offset?
            if clinic.renewal_reminders.filter(
                kind=kind, period_end=period_end, days_before=days_left
            ).exists():
                continue

            recipients = self._recipients(clinic)
            if not recipients:
                # No email on file; don't record so it retries once an email is added.
                skipped += 1
                continue

            subject, body = self._compose(clinic, kind, days_left, period_end, link, price, instapay)

            if dry_run:
                self.stdout.write(
                    f"[dry-run] {clinic.name}: {kind} {days_left}d -> {', '.join(recipients)}"
                )
                sent += 1
                continue

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,
            )
            RenewalReminder.objects.create(
                clinic=clinic, kind=kind, period_end=period_end, days_before=days_left
            )
            sent += 1

        verb = "would send" if dry_run else "sent"
        self.stdout.write(self.style.SUCCESS(
            f"Renewal reminders: {verb} {sent}, skipped {skipped}."
        ))

    def _period(self, clinic):
        """Return (kind, period_end_date) for whichever window applies."""
        if clinic.subscription_status == Clinic.SubscriptionStatus.ACTIVE and clinic.paid_until:
            return RenewalReminder.Kind.PAID, clinic.paid_until
        if clinic.subscription_status == Clinic.SubscriptionStatus.TRIALING and clinic.trial_ends_at:
            return RenewalReminder.Kind.TRIAL, clinic.trial_ends_at
        return None, None

    def _recipients(self, clinic):
        users = clinic.users.filter(is_active=True).exclude(email="")
        admins = [u.email for u in users if u.role == "admin"]
        return admins or [u.email for u in users]

    def _compose(self, clinic, kind, days_left, period_end, link, price, instapay):
        when_en = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
        when_ar = "اليوم" if days_left == 0 else f"خلال {days_left} أيام" if days_left > 2 else f"خلال {days_left} يوم"

        subject = "تذكير بتجديد اشتراك DocuMed — DocuMed renewal reminder"

        if kind == RenewalReminder.Kind.TRIAL:
            en = (
                f"Hello {clinic.name},\n\n"
                f"Your DocuMed free trial ends {when_en} (on {period_end}). "
                f"To keep access to your clinic's records, subscribe for {price} EGP/month: "
                f"send the payment via InstaPay to {instapay}, then submit the reference here:\n"
                f"{link}\n"
            )
            ar = (
                f"مرحباً {clinic.name}،\n\n"
                f"تنتهي تجربتك المجانية في DocuMed {when_ar} (بتاريخ {period_end}). "
                f"للاستمرار في الوصول إلى سجلات عيادتك، اشترك مقابل {price} ج.م. شهرياً: "
                f"أرسل المبلغ عبر إنستاباي إلى {instapay} ثم أدخل الرقم المرجعي هنا:\n"
                f"{link}\n"
            )
        else:
            en = (
                f"Hello {clinic.name},\n\n"
                f"Your DocuMed subscription ends {when_en} (on {period_end}). "
                f"To avoid interruption, send {price} EGP via InstaPay to {instapay}, "
                f"then submit the reference here:\n{link}\n"
            )
            ar = (
                f"مرحباً {clinic.name}،\n\n"
                f"ينتهي اشتراكك في DocuMed {when_ar} (بتاريخ {period_end}). "
                f"لتجنب انقطاع الخدمة، أرسل {price} ج.م. عبر إنستاباي إلى {instapay} "
                f"ثم أدخل الرقم المرجعي هنا:\n{link}\n"
            )

        body = f"{ar}\n— — —\n\n{en}"
        return subject, body
