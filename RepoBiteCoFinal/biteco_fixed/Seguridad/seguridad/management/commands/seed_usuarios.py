"""
Management command: seed_usuarios
==================================
Pobla la base de datos de usuarios (auth_user de Django) con usuarios
de prueba para el experimento del Sprint 2.

Uso:
    python manage.py seed_usuarios
    python manage.py seed_usuarios --cantidad 50
    python manage.py seed_usuarios --limpiar   # borra y recrea
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


USUARIOS_BASE = [
    {"username": "admin@biteco.com",      "email": "admin@biteco.com",      "password": "Admin123!",      "is_staff": True,  "is_superuser": True},
    {"username": "financiero@biteco.com", "email": "financiero@biteco.com", "password": "Financiero123!", "is_staff": False, "is_superuser": False},
    {"username": "analista@biteco.com",   "email": "analista@biteco.com",   "password": "Analista123!",   "is_staff": False, "is_superuser": False},
    {"username": "auditor@biteco.com",    "email": "auditor@biteco.com",    "password": "Auditor123!",    "is_staff": False, "is_superuser": False},
    {"username": "gerente@biteco.com",    "email": "gerente@biteco.com",    "password": "Gerente123!",    "is_staff": False, "is_superuser": False},
]


class Command(BaseCommand):
    help = "Crea usuarios de prueba para el experimento Bite.Co Sprint 2"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cantidad",
            type=int,
            default=0,
            help="Cantidad de usuarios de carga adicionales a crear (usuario1@biteco.com ... usuarioN@biteco.com)",
        )
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina todos los usuarios existentes antes de crear los nuevos (excepto superusuarios del sistema)",
        )

    def handle(self, *args, **options):
        if options["limpiar"]:
            borrados, _ = User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.WARNING(f"  {borrados} usuarios eliminados."))

        # Usuarios base fijos
        creados = 0
        for datos in USUARIOS_BASE:
            if not User.objects.filter(username=datos["username"]).exists():
                User.objects.create_user(
                    username=datos["username"],
                    email=datos["email"],
                    password=datos["password"],
                    is_staff=datos["is_staff"],
                    is_superuser=datos["is_superuser"],
                )
                creados += 1
                self.stdout.write(f"  Creado: {datos['username']}")
            else:
                self.stdout.write(f"  Ya existe: {datos['username']}")

        # Usuarios de carga para Locust/JMeter
        cantidad = options["cantidad"]
        if cantidad > 0:
            self.stdout.write(f"\n  Creando {cantidad} usuarios de carga...")
            for i in range(1, cantidad + 1):
                username = f"usuario{i}@biteco.com"
                if not User.objects.filter(username=username).exists():
                    User.objects.create_user(
                        username=username,
                        email=username,
                        password=f"Pass{i}Segura!",
                    )
                    creados += 1

        total = User.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Listo. {creados} usuarios nuevos creados. Total en BD: {total}"
            )
        )
        self.stdout.write("")
        self.stdout.write("  Credenciales de prueba:")
        self.stdout.write("    admin@biteco.com       / Admin123!")
        self.stdout.write("    financiero@biteco.com  / Financiero123!")
        self.stdout.write("    analista@biteco.com    / Analista123!")
