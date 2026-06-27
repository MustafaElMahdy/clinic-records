from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    """
    Existing clinics with status='active' had no paid_until. Under the new
    is_access_allowed logic, active now requires paid_until >= today, so without
    a value they would be locked out on deploy. Grant them 30 days from today.
    """
    Clinic = apps.get_model("clinics", "Clinic")
    today = timezone.now().date()
    for clinic in Clinic.objects.filter(subscription_status="active", paid_until__isnull=True):
        clinic.paid_until = today + timedelta(days=30)
        clinic.save(update_fields=["paid_until"])


class Migration(migrations.Migration):

    dependencies = [
        ("clinics", "0004_clinic_paid_until_paymentsubmission"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
