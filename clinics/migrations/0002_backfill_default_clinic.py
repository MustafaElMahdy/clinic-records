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
        ("patients", "0002_patient_clinic_and_more"),
        ("visits", "0002_visit_clinic_visit_visits_visi_clinic__7cd38f_idx"),
        ("audit", "0003_auditevent_clinic"),
        ("accounts", "0002_user_clinic"),
    ]

    operations = [
        migrations.RunPython(backfill_default_clinic, migrations.RunPython.noop),
    ]