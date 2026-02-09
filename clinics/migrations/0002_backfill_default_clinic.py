from django.db import migrations


def backfill_default_clinic(apps, schema_editor):
    Clinic = apps.get_model("clinics", "Clinic")
    Patient = apps.get_model("patients", "Patient")
    Visit = apps.get_model("visits", "Visit")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    User = apps.get_model("accounts", "User")

    default_clinic, _ = Clinic.objects.get_or_create(
        name="Default Clinic",
        defaults={"phone": "", "address": ""},
    )

    Patient.objects.filter(clinic__isnull=True).update(clinic=default_clinic)
    Visit.objects.filter(clinic__isnull=True).update(clinic=default_clinic)
    AuditEvent.objects.filter(clinic__isnull=True).update(clinic=default_clinic)
    User.objects.filter(clinic__isnull=True).update(clinic=default_clinic)


class Migration(migrations.Migration):
    dependencies = [
        ("clinics", "0001_initial"),
        ("patients", "0001_initial"),  # adjust if different
        ("visits", "0001_initial"),
        ("audit", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_default_clinic, migrations.RunPython.noop),
    ]