from datetime import date, timedelta
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.mail import send_mail
from django.utils.translation import gettext as _
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.shortcuts import redirect, render
from openpyxl import Workbook

from accounts.models import User
from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from patients.models import Patient
from .forms import ClinicSettingsForm, ClinicSignupForm, PaymentSubmissionForm
from .models import Clinic


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
            messages.success(request, _("Clinic settings saved."))
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


SUBSCRIPTION_FEATURES = [
    "Unlimited patients & visits",
    "Unlimited staff accounts",
    "File attachments (labs, X-rays, docs)",
    "Full audit trail",
    "Data export to Excel",
    "Priority support",
]

@login_required
def subscription(request):
    clinic = getattr(request.user, "clinic", None)

    if request.method == "POST" and clinic is not None:
        form = PaymentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.clinic = clinic
            submission.amount = settings.MONTHLY_PRICE_EGP
            submission.submitted_by = request.user
            submission.save()

            # Notify the owner so they can verify the transfer and approve.
            admin_link = request.build_absolute_uri(
                f"/admin/clinics/paymentsubmission/{submission.pk}/change/"
            )
            send_mail(
                subject=f"[DocuMed] Payment submitted: {clinic.name}",
                message=(
                    f"Clinic: {clinic.name}\n"
                    f"Amount: {submission.amount} EGP\n"
                    f"Reference: {submission.reference}\n"
                    f"Submitted by: {request.user.get_full_name()} ({request.user.email})\n\n"
                    f"Review & approve: {admin_link}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.PAYMENT_NOTIFICATION_EMAIL],
                fail_silently=True,
            )
            messages.success(request, _(
                "Payment submitted. We'll verify it and activate your clinic shortly."
            ))
            return redirect("clinics:subscription")
    else:
        form = PaymentSubmissionForm()

    pending = (
        clinic.payment_submissions.filter(status="pending").exists()
        if clinic else False
    )

    return render(request, "clinics/subscription.html", {
        "clinic": clinic,
        "features": SUBSCRIPTION_FEATURES,
        "form": form,
        "instapay_address": settings.INSTAPAY_ADDRESS,
        "price": settings.MONTHLY_PRICE_EGP,
        "pending": pending,
    })


def clinic_signup(request):
    if request.user.is_authenticated:
        return redirect("patients:list")

    if request.method == "POST":
        form = ClinicSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                clinic = Clinic.objects.create(
                    name=form.cleaned_data["clinic_name"],
                    trial_ends_at=date.today() + timedelta(days=14),
                    subscription_status=Clinic.SubscriptionStatus.TRIALING,
                )
                email = form.cleaned_data["email"]
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=form.cleaned_data["password"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    role="admin",
                    clinic=clinic,
                )
            login(request, user)
            messages.success(request, _("Welcome to DocuMed! Your 14-day free trial has started."))
            return redirect("patients:list")
    else:
        form = ClinicSignupForm()

    return render(request, "registration/signup.html", {"form": form})


# Allowlisted marketing CTA events. Anything not in here is ignored, so the
# public endpoint can't be used to write arbitrary data.
TRACKED_EVENTS = {
    "nav_features": "Nav: Features",
    "nav_howitworks": "Nav: How It Works",
    "nav_pricing": "Nav: Pricing",
    "nav_login": "Nav: Log in",
    "trial_nav": "Start trial · nav",
    "trial_hero": "Start trial · hero",
    "trial_pricing": "Start trial · pricing",
    "trial_cta": "Start trial · final CTA",
}


@csrf_exempt
@require_POST
def track_event(request):
    """Anonymous first-party click beacon. Records only allowlisted event names."""
    name = (request.POST.get("name") or "").strip()
    if name in TRACKED_EVENTS:
        from .models import ClickEvent
        ClickEvent.objects.create(name=name, page=(request.POST.get("page") or "")[:200])
    return HttpResponse(status=204)


def _is_owner(user):
    return user.is_authenticated and user.is_superuser


@user_passes_test(_is_owner)
def owner_dashboard(request):
    """Platform-wide business metrics for the product owner (superuser only)."""
    from visits.models import Visit
    from .models import PaymentSubmission, ClickEvent

    now = timezone.now()
    today = now.date()
    clinics = Clinic.objects.all()

    total = clinics.count()
    active_trials = clinics.filter(
        subscription_status=Clinic.SubscriptionStatus.TRIALING, trial_ends_at__gte=today
    ).count()
    lapsed_trials = clinics.filter(
        subscription_status=Clinic.SubscriptionStatus.TRIALING, trial_ends_at__lt=today
    ).count()
    paying = clinics.filter(
        subscription_status=Clinic.SubscriptionStatus.ACTIVE, paid_until__gte=today
    ).count()
    lapsed_paid = clinics.filter(
        subscription_status=Clinic.SubscriptionStatus.ACTIVE, paid_until__lt=today
    ).count()
    expired = clinics.filter(
        subscription_status=Clinic.SubscriptionStatus.EXPIRED
    ).count()

    signups_7 = clinics.filter(created_at__gte=now - timedelta(days=7)).count()
    signups_30 = clinics.filter(created_at__gte=now - timedelta(days=30)).count()

    conversion = round(paying / total * 100, 1) if total else 0
    mrr = paying * settings.MONTHLY_PRICE_EGP
    pending_payments = PaymentSubmission.objects.filter(
        status=PaymentSubmission.Status.PENDING
    ).count()

    # Recent signups with a human-readable status.
    recent_rows = []
    for c in clinics.order_by("-created_at")[:12]:
        if c.subscription_status == Clinic.SubscriptionStatus.ACTIVE and c.paid_until and c.paid_until >= today:
            status = f"Paying · {c.paid_days_remaining}d left"
        elif c.subscription_status == Clinic.SubscriptionStatus.TRIALING and c.trial_ends_at and c.trial_ends_at >= today:
            status = f"Trial · {c.trial_days_remaining}d left"
        elif c.subscription_status == Clinic.SubscriptionStatus.TRIALING:
            status = "Trial expired"
        else:
            status = "Inactive"
        recent_rows.append({"clinic": c, "status": status})

    # Website click counts (all-time + last 7 days), in a fixed friendly order.
    all_counts = {r["name"]: r["total"] for r in
                  ClickEvent.objects.values("name").annotate(total=Count("id"))}
    week_counts = {r["name"]: r["total"] for r in
                   ClickEvent.objects.filter(created_at__gte=now - timedelta(days=7))
                   .values("name").annotate(total=Count("id"))}
    click_rows = [
        {"label": label, "total": all_counts.get(name, 0), "week": week_counts.get(name, 0)}
        for name, label in TRACKED_EVENTS.items()
    ]

    return render(request, "clinics/owner_dashboard.html", {
        "click_rows": click_rows,
        "total": total,
        "active_trials": active_trials,
        "lapsed_trials": lapsed_trials,
        "paying": paying,
        "lapsed_paid": lapsed_paid,
        "expired": expired,
        "signups_7": signups_7,
        "signups_30": signups_30,
        "conversion": conversion,
        "mrr": mrr,
        "price": settings.MONTHLY_PRICE_EGP,
        "pending_payments": pending_payments,
        "total_patients": Patient.objects.count(),
        "total_visits": Visit.objects.count(),
        "recent_rows": recent_rows,
    })
