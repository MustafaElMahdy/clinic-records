from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("visits", "0003_alter_visit_clinic"),
    ]

    operations = [
        # Single-column visit_datetime index made redundant by the composite
        # (clinic, visit_datetime) index added in 0002. All visit queries filter
        # by clinic_id first via middleware, so the composite is always used.
        migrations.RemoveIndex(
            model_name="visit",
            name="visits_visi_visit_d_348ffd_idx",
        ),
    ]
