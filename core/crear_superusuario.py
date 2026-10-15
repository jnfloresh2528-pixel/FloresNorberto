# core/management/commands/crear_superusuario.py
"""Crea el superusuario de producción desde variables de entorno.

Uso local:
    python manage.py crear_superusuario

Uso en Render (build command):
    python manage.py crear_superusuario

Variables de entorno requeridas:
    DJANGO_SUPERUSER_USERNAME
    DJANGO_SUPERUSER_EMAIL
    DJANGO_SUPERUSER_PASSWORD

El comando es idempotente: si el usuario ya existe, no lo duplica
ni falla; solo actualiza la contraseña si se desea.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea el superusuario usando variables de entorno (idempotente)."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email    = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                "Variables DJANGO_SUPERUSER_USERNAME / _PASSWORD no definidas. "
                "Se omite la creación del superusuario."
            ))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True,
                      "is_superuser": True},
        )

        # Garantizar privilegios y contraseña
        user.email        = email or user.email
        user.is_staff     = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Superusuario '{username}' creado correctamente."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Superusuario '{username}' ya existía; contraseña actualizada."
            ))