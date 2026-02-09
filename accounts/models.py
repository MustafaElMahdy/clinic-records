from django.contrib.auth.models import AbstractUser
from django.db import models
from clinics.models import Clinic


class User(AbstractUser):
    ROLE_CHOICES = (
        ("doctor", "Doctor"),
        ("assistant", "Assistant"),
        ("admin", "Admin"),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="assistant")

    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )