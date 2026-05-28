from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0005_remove_unique_phone_per_clinic"),
    ]

    operations = [
        # Single-column indexes made redundant by composite (clinic, X) indexes added
        # in 0002_patient_clinic_and_more. All patient queries filter by clinic_id first
        # via middleware, so the composites are always preferred by the query planner.
        migrations.RemoveIndex(
            model_name="patient",
            name="patients_pa_normali_d6dbc0_idx",
        ),
        migrations.RemoveIndex(
            model_name="patient",
            name="patients_pa_phone_fc49bb_idx",
        ),
        migrations.RemoveIndex(
            model_name="patient",
            name="patients_pa_nationa_70cc77_idx",
        ),
        # Explicit (clinic, national_id) index is a true duplicate of the implicit index
        # created by the unique_national_id_per_clinic constraint (added in 0004).
        # The constraint's index is strictly better: it enforces uniqueness and serves
        # as a lookup index. Keeping both wastes write overhead on every INSERT/UPDATE.
        migrations.RemoveIndex(
            model_name="patient",
            name="patients_pa_clinic__882269_idx",
        ),
    ]
